"""
Data Fetcher — alle Datenquellen parallel
Erweitert um Liquidity-Indikatoren (CPI, M2, WALCL) + DXY für Phase 1
"""

import os
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
            r = requests.get(url, headers=headers or {}, params=params, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Fetch error {url[:60]}: {e}")
            return {}

    def _get_text(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=self.timeout)
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
            print(f"  No valid expiry for {ticker}")
            return []
        url = "https://api.tradier.com/v1/markets/options/chains"
        try:
            r = requests.get(url, headers=self.headers_tradier,
                             params={"symbol": ticker, "expiration": expiry, "greeks": "true"},
                             timeout=self.timeout)
            if r.status_code != 200:
                print(f"  Tradier HTTP {r.status_code} for {ticker}")
                return []
            data = r.json()
            chain = (data.get("options") or {}).get("option") or []
            result = chain if isinstance(chain, list) else [chain]
            print(f"  Tradier {ticker}: {len(result)} options (expiry {expiry})")
            return result
        except Exception as e:
            print(f"  Tradier chain error {ticker}: {e}")
            return []

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
        try:
            df = yf.download(ticker, period="1mo", auto_adjust=True, progress=False)
            if df.empty:
                return []
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(-1)
            df.columns = [str(c).strip().lower() for c in df.columns]
            result = []
            for _, row in df.iterrows():
                try:
                    result.append({
                        "h": float(row.get("high", row.get("High", 0))),
                        "l": float(row.get("low", row.get("Low", 0))),
                        "c": float(row.get("close", row.get("Close", 0))),
                        "v": float(row.get("volume", row.get("Volume", 0))),
                    })
                except:
                    continue
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
            return {
                "current": float(rows[0].get("value", 0)),
                "previous": float(rows[1].get("value", 0)) if len(rows) > 1 else 0,
                "delta": float(rows[0].get("value", 0)) - float(rows[1].get("value", 0)) if len(rows) > 1 else 0,
                "as_of": rows[0].get("period", ""),
            }
        return {"current": 0, "previous": 0, "delta": 0, "as_of": ""}

    # ── COT – ROBUSTE VERSION mit Fallback + besserem Parsing ─────────────
    def fetch_cot(self, cot_code):
        if not cot_code:
            return {"net_commercial": 0, "long": 0, "short": 0, "as_of": "no_code"}

        url = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
        try:
            import io
            import csv
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

            reader = csv.DictReader(io.StringIO(resp.text))
            rows = [r for r in reader if r.get("CFTC_Commodity_Code", "").strip() == cot_code]

            if not rows:
                print(f"  [COT] ⚠️  Keine Daten für Code {cot_code} gefunden")
                return {"net_commercial": 0, "long": 0, "short": 0, "as_of": "no_data"}

            # Sortiere nach Datum (neueste zuerst)
            rows.sort(key=lambda r: r.get("Report_Date_as_YYYY-MM-DD", ""), reverse=True)

            # Nimm neuesten Report
            r = rows[0]
            comm_long = int(r.get("Comm_Positions_Long_All", 0) or 0)
            comm_short = int(r.get("Comm_Positions_Short_All", 0) or 0)
            as_of = r.get("Report_Date_as_YYYY-MM-DD", "")

            net = comm_long - comm_short

            print(f"  [COT] ✅ {cot_code} | Net-Commercial: {net:,} | as-of: {as_of}")

            # Fallback: Wenn aktueller Report 0 ist → nimm vorherige Woche
            if net == 0 and len(rows) > 1:
                r2 = rows[1]
                comm_long2 = int(r2.get("Comm_Positions_Long_All", 0) or 0)
                comm_short2 = int(r2.get("Comm_Positions_Short_All", 0) or 0)
                net2 = comm_long2 - comm_short2
                as_of2 = r2.get("Report_Date_as_YYYY-MM-DD", "")
                print(f"  [COT] ⚠️  Net=0 → Fallback auf Vorwoche: {net2:,} | {as_of2}")
                return {
                    "net_commercial": net2,
                    "long": comm_long2,
                    "short": comm_short2,
                    "as_of": as_of2 + " (fallback)",
                }

            return {
                "net_commercial": net,
                "long": comm_long,
                "short": comm_short,
                "as_of": as_of,
            }

        except Exception as e:
            print(f"  [COT] ❌ Fetch error {cot_code}: {e}")
            return {"net_commercial": 0, "long": 0, "short": 0, "as_of": "error"}

    # ── FRED – erweitert für Liquidity Score (Phase 1) ───────────────
    def fetch_fred(self):
        results = {}
        series = {
            "fed_funds_rate": "FEDFUNDS",
            "real_yield_10y": "DFII10",
            "dxy": "DTWEXBGS",
            "cpi": "CPIAUCSL",
            "m2": "M2SL",
            "walcl": "WALCL",
        }
        for name, sid in series.items():
            url = "https://api.stlouisfed.org/fred/series/observations"
            data = self._get(url, params={
                "series_id": sid,
                "api_key": self.fred_key,
                "sort_order": "desc",
                "limit": 12,
                "file_type": "json"
            })
            obs = data.get("observations", [])
            if obs:
                try:
                    results[name] = float(obs[0]["value"])
                except:
                    results[name] = 0.0
            else:
                results[name] = 0.0
        return results

    # ── RSS ──────────────────────────────────────────────────────────
    def fetch_rss(self, query):
        url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
        return self._get_text(url)

    # ── yfinance ─────────────────────────────────────────────────────
    def fetch_yfinance(self, ticker, period="2y"):
        try:
            df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
            if df.empty:
                return []
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(-1)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.reset_index()
            return df.to_dict("records")
        except Exception as e:
            print(f"  yfinance error {ticker}: {e}")
            return []

    # ── Historische Optionspreise ────────────────────────────────────
    def fetch_historical_option(self, contract_symbol: str, period: str = "120d"):
        try:
            print(f"    Fetching historical option data for {contract_symbol} ({period})...")
            opt = yf.Ticker(contract_symbol)
            hist = opt.history(period=period, auto_adjust=True)
            if hist.empty:
                print(f"    ⚠️ No historical data for {contract_symbol}")
                return []
            hist = hist.reset_index()
            result = hist[["Date", "Open", "High", "Low", "Close", "Volume"]].to_dict("records")
            print(f"    ✅ {len(result)} days of real option prices for {contract_symbol}")
            return result
        except Exception as e:
            print(f"    Hist option {contract_symbol} error: {e}")
            return []

    # ── Main fetch_all ───────────────────────────────────────────────
    def fetch_all(self):
        cfg_wl = self.cfg["watchlist"]
        all_tickers = list({t for seg in cfg_wl.values() for t in seg["tickers"]})

        result = {
            "quotes": {}, "candles": {}, "options_chains": {}, "tradier_quotes": {},
            "eia": {}, "cot": {}, "fred": {}, "rss": {}, "yfinance": {},
            "as_of": {}, "historical_options": {}
        }

        def fetch_ticker_data(ticker):
            print(f"    Fetching {ticker}...")
            return {
                "ticker": ticker,
                "quote": self.fetch_finnhub_quote(ticker),
                "tquote": self.fetch_tradier_quote(ticker),
                "candles": self.fetch_finnhub_candles(ticker),
                "chain": self.fetch_tradier_chain(ticker),
            }

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(fetch_ticker_data, t): t for t in all_tickers}
            for f in as_completed(futures):
                d = f.result()
                t = d["ticker"]
                result["quotes"][t] = d["quote"]
                result["tradier_quotes"][t] = d["tquote"]
                result["candles"][t] = d["candles"]
                result["options_chains"][t] = d["chain"]

        result["fred"] = self.fetch_fred()

        for seg, seg_cfg in cfg_wl.items():
            if seg_cfg.get("eia_series"):
                eia_data = self.fetch_eia(seg_cfg["eia_series"][0])
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
