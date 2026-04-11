"""
Data Fetcher — alle Datenquellen parallel
Speichert as-of Timestamps für Look-Ahead-Bias-Prävention (FIX-1)
"""

import os
import json
import datetime
import requests
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET


class DataFetcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tradier_key = os.environ.get("TRADIER_KEY", "")
        self.finnhub_key = os.environ.get("FINNHUB_KEY", "")
        self.eia_key = os.environ.get("EIA_KEY", "")
        self.fred_key = os.environ.get("FRED_KEY", "")
        self.headers_tradier = {
            "Authorization": f"Bearer {self.tradier_key}",
            "Accept": "application/json",
        }
        self.timeout = 15

    def _get(self, url, headers=None, params=None):
        try:
            r = requests.get(url, headers=headers or {}, params=params,
                             timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Fetch error {url[:60]}: {e}")
            return {}

    def _get_text(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=self.timeout)
            return r.text
        except Exception as e:
            print(f"  Fetch error {url[:60]}: {e}")
            return ""

    # ── Tradier ──────────────────────────────────────────────────────

    def fetch_tradier_quote(self, ticker):
        url = "https://api.tradier.com/v1/markets/quotes"
        data = self._get(url, self.headers_tradier, {"symbols": ticker})
        return data.get("quotes", {}).get("quote", {})

    def fetch_tradier_chain(self, ticker):
        today = datetime.date.today()
        expiry = self._next_monthly_expiry(today, min_dte=21)
        if not expiry:
            return []
        url = "https://api.tradier.com/v1/markets/options/chains"
        data = self._get(url, self.headers_tradier,
                         {"symbol": ticker, "expiration": expiry, "greeks": "true"})
        chain = (data.get("options") or {}).get("option") or []
        return chain if isinstance(chain, list) else [chain]

    def _next_monthly_expiry(self, today, min_dte=21):
        for m in range(1, 5):
            month = (today.month - 1 + m) % 12 + 1
            year = today.year + ((today.month - 1 + m) // 12)
            first = datetime.date(year, month, 1)
            first_fri = first + datetime.timedelta(days=(4 - first.weekday()) % 7)
            third_fri = first_fri + datetime.timedelta(weeks=2)
            if (third_fri - today).days >= min_dte:
                return third_fri.strftime("%Y-%m-%d")
        return None

    # ── Finnhub ──────────────────────────────────────────────────────

    def fetch_finnhub_quote(self, ticker):
        url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={self.finnhub_key}"
        return self._get(url)

    def fetch_finnhub_candles(self, ticker, days=22):
        """Fallback: use yfinance for historical candles (Finnhub free tier blocks this)."""
        try:
            import yfinance as yf
            df = yf.download(ticker, period="1mo", auto_adjust=True, progress=False)
            if df.empty:
                return []
            result = []
            for _, row in df.iterrows():
                result.append({
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                    "v": float(row["Volume"]),
                })
            return result
        except Exception as e:
            print(f"  yfinance candles error {ticker}: {e}")
            return []

    # ── EIA ──────────────────────────────────────────────────────────

    def fetch_eia(self, series_id):
        url = f"https://api.eia.gov/v2/seriesid/{series_id}"
        data = self._get(url, params={"api_key": self.eia_key, "length": 4})
        rows = (data.get("response") or {}).get("data") or []
        if rows:
            last_release = rows[0].get("period", "")
            return {
                "current": float(rows[0].get("value", 0)),
                "previous": float(rows[1].get("value", 0)) if len(rows) > 1 else 0,
                "delta": float(rows[0].get("value", 0)) - float(rows[1].get("value", 0)) if len(rows) > 1 else 0,
                "as_of": last_release,
            }
        return {"current": 0, "previous": 0, "delta": 0, "as_of": ""}

    # ── CFTC COT ─────────────────────────────────────────────────────

    def fetch_cot(self, cot_code):
        if not cot_code:
            return {"net_commercial": 0, "long": 0, "short": 0, "as_of": ""}
        try:
            url = (
                f"https://publicreporting.cftc.gov/api/explore/dataset/"
                f"com-disagg-report-legacy-futures-only/exports/json"
                f"?where=cftc_commodity_code%3D{cot_code}"
                f"&order_by=report_date_as_yyyy_mm_dd+DESC&limit=2"
            )
            data = self._get(url)
            records = data if isinstance(data, list) else data.get("results", [])
            if not records:
                return {"net_commercial": 0, "long": 0, "short": 0, "as_of": ""}
            r = records[0]
            net = (int(r.get("comm_positions_long_all", 0)) -
                   int(r.get("comm_positions_short_all", 0)))
            return {
                "net_commercial": net,
                "long": int(r.get("comm_positions_long_all", 0)),
                "short": int(r.get("comm_positions_short_all", 0)),
                "as_of": r.get("report_date_as_yyyy_mm_dd", ""),
            }
        except Exception as e:
            print(f"  COT fetch error {cot_code}: {e}")
            return {"net_commercial": 0, "long": 0, "short": 0, "as_of": ""}

    # ── FRED ─────────────────────────────────────────────────────────

    def fetch_fred(self):
        results = {}
        series = {
            "fed_funds_rate": "FEDFUNDS",
            "real_yield_10y": "DFII10",
            "dxy": "DTWEXBGS",
        }
        for name, sid in series.items():
            url = f"https://api.stlouisfed.org/fred/series/observations"
            data = self._get(url, params={
                "series_id": sid, "api_key": self.fred_key,
                "sort_order": "desc", "limit": 2,
                "file_type": "json",
            })
            obs = data.get("observations", [])
            if obs:
                try:
                    results[name] = float(obs[0]["value"])
                except (ValueError, KeyError):
                    results[name] = 0.05
            else:
                results[name] = 0.05
        return results

    # ── Google News RSS ───────────────────────────────────────────────

    def fetch_rss(self, query):
        url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
        return self._get_text(url)

    # ── yfinance historical ───────────────────────────────────────────

    def fetch_yfinance(self, ticker, period="2y"):
        try:
            df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
            if df.empty:
                return []
            return df[["Open", "High", "Low", "Close", "Volume"]].reset_index().to_dict("records")
        except Exception as e:
            print(f"  yfinance error {ticker}: {e}")
            return []

    # ── Main fetch_all ────────────────────────────────────────────────

    def fetch_all(self):
        cfg_wl = self.cfg["watchlist"]
        all_tickers = list({t for seg in cfg_wl.values() for t in seg["tickers"]})
        result = {
            "quotes": {},
            "candles": {},
            "options_chains": {},
            "eia": {},
            "cot": {},
            "fred": {},
            "rss": {},
            "yfinance": {},
            "as_of": {},
        }

        def fetch_ticker_data(ticker):
            print(f"    Fetching {ticker}...")
            return {
                "ticker": ticker,
                "quote": self.fetch_finnhub_quote(ticker),
                "candles": self.fetch_finnhub_candles(ticker),
                "chain": self.fetch_tradier_chain(ticker),
            }

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(fetch_ticker_data, t): t for t in all_tickers}
            for f in as_completed(futures):
                d = f.result()
                t = d["ticker"]
                result["quotes"][t] = d["quote"]
                result["candles"][t] = d["candles"]
                result["options_chains"][t] = d["chain"]

        result["fred"] = self.fetch_fred()

        for seg, seg_cfg in cfg_wl.items():
            eia_series = seg_cfg.get("eia_series", [])
            if eia_series:
                eia_data = self.fetch_eia(eia_series[0])
                result["eia"][seg] = eia_data
                result["as_of"][f"eia_{seg}"] = eia_data.get("as_of", "")

            cot_data = self.fetch_cot(seg_cfg["cot_code"])
            result["cot"][seg] = cot_data
            result["as_of"][f"cot_{seg}"] = cot_data.get("as_of", "")

            result["rss"][seg] = self.fetch_rss(seg_cfg["rss_query"])
            result["yfinance"][seg] = self.fetch_yfinance(seg_cfg["tickers"][0])

        result["as_of"]["tradier"] = datetime.datetime.utcnow().isoformat() + "Z"
        result["as_of"]["fred"] = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        return result
