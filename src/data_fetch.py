"""
Data Fetcher v2 — mehrere Expirations (DTE-gefiltert), yfinance HV, EIA, FRED
"""

import datetime
import requests
import yfinance as yf
import numpy as np
import os
import pandas as pd

from cot.pycot_analyzer import PyCOTAnalyzer


class DataFetcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self._dte_min = cfg.get("thresholds", {}).get("options_dte_min", 21)
        self._dte_max = cfg.get("thresholds", {}).get("options_dte_max", 180)

    def fetch_all(self):
        raw_data = {}
        raw_data["quotes"]          = self.fetch_quotes()
        raw_data["tradier_quotes"]  = self.fetch_tradier_quotes()
        raw_data["options_chains"]  = self.fetch_options_chains()
        raw_data["yfinance"]        = self.fetch_yfinance()
        raw_data["eia"]             = self.fetch_eia()
        raw_data["fred"]            = self.fetch_fred()
        raw_data["cot"]             = self.fetch_cot_data()
        raw_data["as_of"]           = {"timestamp": datetime.datetime.utcnow().isoformat() + "Z"}
        raw_data["spot_prices"]     = self._validate_spot_prices(raw_data)
        return raw_data

    # ------------------------------------------------------------------ quotes

    def fetch_quotes(self):
        api_key = os.getenv("FINNHUB_KEY", "")
        if not api_key:
            print("  ❌ FINNHUB_KEY fehlt")
            return {}
        results = {}
        for seg in self.cfg.get("watchlist", {}):
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
            try:
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data and data.get("c"):
                        results[ticker] = data
            except Exception as e:
                print(f"  [Finnhub] {ticker}: {e}")
        return results

    def fetch_tradier_quotes(self):
        api_key = os.getenv("TRADIER_KEY", "")
        if not api_key:
            print("  ❌ TRADIER_KEY fehlt")
            return {}
        results = {}
        for seg in self.cfg.get("watchlist", {}):
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            url = f"https://api.tradier.com/v1/markets/quotes?symbols={ticker}"
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
            try:
                r = self.session.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    q = data.get("quotes", {}).get("quote", {})
                    if q:
                        results[ticker] = q
            except Exception as e:
                print(f"  [Tradier quote] {ticker}: {e}")
        return results

    # --------------------------------------------------------- options chains

    def fetch_options_chains(self):
        """
        Fetches options for expirations within DTE range (dte_min–dte_max).
        Returns flat list per ticker with days_to_expiration populated.
        Flattens Tradier greeks sub-dict into top-level fields.
        """
        api_key = os.getenv("TRADIER_KEY", "")
        if not api_key:
            return {}

        headers  = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        results  = {}
        today    = datetime.date.today()

        for seg in self.cfg.get("watchlist", {}):
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            if ticker in results:
                continue  # already fetched (duplicate tickers across segments)

            exp_url = f"https://api.tradier.com/v1/markets/options/expirations?symbol={ticker}"
            try:
                r_exp = self.session.get(exp_url, headers=headers, timeout=10)
                if r_exp.status_code != 200:
                    continue
                all_exps = r_exp.json().get("expirations", {}).get("date", [])
                if not all_exps:
                    continue
            except Exception as e:
                print(f"  ❌ Tradier expirations {ticker}: {e}")
                continue

            # Filter expirations by DTE range
            valid_exps = []
            for exp_str in all_exps:
                try:
                    exp_date = datetime.date.fromisoformat(exp_str)
                    dte = (exp_date - today).days
                    if self._dte_min <= dte <= self._dte_max:
                        valid_exps.append((exp_str, dte))
                except:
                    continue

            if not valid_exps:
                print(f"  ⚠️  {ticker}: keine Expiration in {self._dte_min}–{self._dte_max} DTE")
                continue

            # Fetch up to 4 matching expirations to get a range of contracts
            all_options = []
            for exp_str, dte in valid_exps[:4]:
                chain_url = (
                    f"https://api.tradier.com/v1/markets/options/chains"
                    f"?symbol={ticker}&expiration={exp_str}&greeks=true"
                )
                try:
                    r_chain = self.session.get(chain_url, headers=headers, timeout=10)
                    if r_chain.status_code != 200:
                        continue
                    chain_data = r_chain.json().get("options", {}).get("option", [])
                    if not chain_data:
                        continue

                    for opt in chain_data:
                        # Flatten greeks sub-dict to top level
                        greeks = opt.pop("greeks", {}) or {}
                        opt["delta"]              = greeks.get("delta", 0)
                        opt["gamma"]              = greeks.get("gamma", 0)
                        opt["theta"]              = greeks.get("theta", 0)
                        opt["vega"]               = greeks.get("vega", 0)
                        opt["implied_volatility"]  = greeks.get("mid_iv", 0)
                        opt["days_to_expiration"]  = dte

                    all_options.extend(chain_data)
                except Exception as e:
                    print(f"  ❌ Tradier chain {ticker} {exp_str}: {e}")
                    continue

            if all_options:
                results[ticker] = all_options
                print(f"  ✅ Options {ticker}: {len(all_options)} Kontrakte aus {len(valid_exps[:4])} Expirations")

        return results

    # ---------------------------------------- yfinance underlying + HV

    def fetch_yfinance(self):
        """
        Fetches 90-day price history for all underlying ETFs.
        Pre-computes 20-day HV (annualized) and stores as {ticker}_hv20.
        """
        all_tickers = set()
        for seg_cfg in self.cfg.get("watchlist", {}).values():
            for t in seg_cfg.get("tickers", []):
                all_tickers.add(t)

        results = {}
        for ticker in sorted(all_tickers):
            try:
                df = yf.Ticker(ticker).history(period="90d")
                if df.empty:
                    print(f"  [yfinance] {ticker}: leer")
                    continue

                df = df.reset_index()
                records = []
                for _, row in df.iterrows():
                    records.append({
                        "Date":   str(row.get("Date", "")),
                        "Open":   float(row.get("Open", 0)),
                        "High":   float(row.get("High", 0)),
                        "Low":    float(row.get("Low", 0)),
                        "Close":  float(row.get("Close", 0)),
                        "Volume": int(row.get("Volume", 0)),
                    })
                results[ticker] = records

                # Pre-compute 20-day HV
                closes = [r["Close"] for r in records if r["Close"] > 0]
                if len(closes) >= 21:
                    arr = np.array(closes[-21:])
                    log_ret = np.log(arr[1:] / arr[:-1])
                    hv = float(log_ret.std() * np.sqrt(252))
                    results[f"{ticker}_hv20"] = max(hv, 0.05)
                    print(f"  [yfinance] {ticker}: {len(records)} Tage | HV20={hv:.1%}")
                else:
                    print(f"  [yfinance] {ticker}: {len(records)} Tage (zu wenig für HV)")

            except Exception as e:
                print(f"  [yfinance] {ticker}: {e}")

        return results

    # -------------------------------------------------------------------- EIA

    def fetch_eia(self):
        """
        Enhanced EIA: 12-week history, Z-Score vs. 4-week baseline, signal classification.
        Feeds both edge score multiplier AND MC drift via compute_eia_impact().
        """
        api_key = os.getenv("EIA_KEY", "")
        if not api_key:
            print("  ⚠️  EIA_KEY fehlt — EIA-Daten übersprungen")
            return {}

        results = {}
        for seg, seg_cfg in self.cfg.get("watchlist", {}).items():
            for series_id in seg_cfg.get("eia_series", []):
                try:
                    url = (
                        f"https://api.eia.gov/v2/seriesid/{series_id}"
                        f"?api_key={api_key}&length=12"
                    )
                    r = self.session.get(url, timeout=12)
                    if r.status_code != 200:
                        continue
                    data = r.json().get("response", {}).get("data", [])
                    if len(data) < 4:
                        continue

                    data_sorted = sorted(data, key=lambda x: x.get("period", ""), reverse=True)
                    values = [float(d.get("value", 0) or 0) for d in data_sorted]

                    latest = values[0]
                    prev   = values[1]
                    delta  = latest - prev

                    # Z-Score: latest vs. weeks 4–11 as baseline (avoids look-ahead)
                    baseline = values[4:] if len(values) >= 8 else values[2:]
                    if baseline and np.std(baseline) > 0:
                        z_score = (latest - np.mean(baseline)) / np.std(baseline)
                    else:
                        z_score = 0.0

                    # Seasonal surprise: this week's change vs. avg abs-change
                    recent_changes = [abs(values[i] - values[i+1]) for i in range(1, min(5, len(values)-1))]
                    avg_change = np.mean(recent_changes) if recent_changes else 1.0
                    surprise = delta / (avg_change + 1.0)

                    # Signal classification
                    if z_score < -1.5 and delta < -5000:
                        signal = "STRONG_BULLISH"
                    elif z_score < -0.8 and delta < -2000:
                        signal = "BULLISH"
                    elif z_score > 1.5 and delta > 5000:
                        signal = "STRONG_BEARISH"
                    elif z_score > 0.8 and delta > 2000:
                        signal = "BEARISH"
                    else:
                        signal = "NEUTRAL"

                    if seg not in results:
                        results[seg] = {}
                    results[seg][series_id] = {
                        "latest":     round(latest, 1),
                        "delta":      round(delta, 1),
                        "z_score":    round(z_score, 2),
                        "surprise":   round(surprise, 2),
                        "pct_change": round(delta / prev * 100, 2) if prev else 0,
                        "period":     data_sorted[0].get("period", ""),
                        "signal":     signal,
                    }
                    print(f"  [EIA] {seg}/{series_id}: {latest:.0f} Δ{delta:+.0f} | Z={z_score:.2f} | {signal}")
                except Exception as e:
                    print(f"  [EIA] {series_id}: {e}")

        return results

    # ------------------------------------------------------------------- FRED

    def fetch_fred(self):
        """Fetches key macro indicators: 10y yield, Fed Funds, DXY, CPI."""
        api_key = os.getenv("FRED_KEY", "")
        if not api_key:
            print("  ⚠️  FRED_KEY fehlt — FRED-Daten übersprungen")
            return {}

        series = {
            "DGS10":    "treasury_10y",
            "FEDFUNDS": "fed_funds_rate",
            "DTWEXBGS": "dollar_index",
            "CPIAUCSL": "cpi",
        }
        results = {}
        for series_id, name in series.items():
            try:
                url = (
                    f"https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={series_id}&api_key={api_key}"
                    f"&sort_order=desc&limit=2&file_type=json"
                )
                r = self.session.get(url, timeout=12)
                if r.status_code != 200:
                    continue
                obs = r.json().get("observations", [])
                if not obs:
                    continue
                val = obs[0].get("value", ".")
                if val != ".":
                    results[name] = round(float(val), 4)
                    print(f"  [FRED] {name}: {val}")
            except Exception as e:
                print(f"  [FRED] {series_id}: {e}")

        return results

    # -------------------------------------------------------------------- COT

    def fetch_cot_data(self):
        analyzer = PyCOTAnalyzer(self.cfg)
        cot_data = {}
        seen = set()
        for seg in self.cfg.get("watchlist", {}):
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            if ticker in seen:
                continue
            seen.add(ticker)
            cot_cfg = self.cfg["watchlist"][seg]
            data = analyzer.get_cot_data(ticker, cot_cfg)
            cot_data[ticker] = data
            print(f"  [COT] {ticker} → {data.get('signal_strength')} | z={data.get('z_score',0):.2f}")
        return cot_data

    # --------------------------------------------------- spot price resolution

    def _validate_spot_prices(self, raw_data):
        spots = {}
        for seg in self.cfg.get("watchlist", {}):
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            spots[ticker] = self._get_spot_price(ticker, raw_data)
        return spots

    def _get_spot_price(self, ticker, raw_data):
        # 1. Tradier
        tr = raw_data.get("tradier_quotes", {}).get(ticker, {})
        for key in ["last", "bid", "ask"]:
            v = tr.get(key)
            if v and float(v) > 0:
                return float(v)
        # 2. Finnhub
        fh = raw_data.get("quotes", {}).get(ticker, {})
        for key in ["c", "pc"]:
            v = fh.get(key)
            if v and float(v) > 0:
                return float(v)
        # 3. yfinance history (last close)
        yf_hist = raw_data.get("yfinance", {}).get(ticker, [])
        if yf_hist:
            last_close = yf_hist[-1].get("Close", 0)
            if last_close > 0:
                return float(last_close)
        print(f"  ⚠️  No spot price for {ticker}")
        return 0.0

    # ------------------------------------------------------ option history

    def fetch_historical_option(self, contract_symbol, period="120d"):
        """Kept for compatibility — underlying history now preferred for backtest."""
        try:
            df = yf.Ticker(contract_symbol).history(period=period)
            if df.empty:
                return []
            return df.reset_index().to_dict("records")
        except Exception as e:
            print(f"    ⚠️ yfinance option {contract_symbol}: {e}")
            return []
