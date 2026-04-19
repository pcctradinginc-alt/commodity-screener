"""
Data Fetcher – Diagnose-Modus für Spot-Preise (Tradier + Finnhub)
"""

import datetime
import requests
import yfinance as yf
import os
import pandas as pd

from cot.pycot_analyzer import PyCOTAnalyzer


class DataFetcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_all(self):
        raw_data = {}

        raw_data["quotes"] = self.fetch_quotes()           # Finnhub
        raw_data["tradier_quotes"] = self.fetch_tradier_quotes()
        raw_data["candles"] = self.fetch_candles()
        raw_data["options_chains"] = self.fetch_options_chains()
        raw_data["eia"] = self.fetch_eia()
        raw_data["cot"] = self.fetch_cot_data()
        raw_data["fred"] = self.fetch_fred()
        raw_data["rss"] = self.fetch_rss()
        raw_data["yfinance"] = self.fetch_yfinance()
        raw_data["as_of"] = {"timestamp": datetime.datetime.utcnow().isoformat() + "Z"}

        raw_data["spot_prices"] = self._validate_spot_prices(raw_data)

        return raw_data

    # ─────────────────────────────────────────────────────────────
    # Diagnose-Modus für Finnhub
    # ─────────────────────────────────────────────────────────────
    def fetch_quotes(self):
        """Finnhub – mit vollem Debug"""
        api_key = os.getenv("FINNHUB_KEY")
        key_len = len(api_key) if api_key else 0
        print(f"  [DEBUG] FINNHUB_KEY geladen? Länge = {key_len}")

        if key_len == 0:
            print("  ❌ Finnhub Key fehlt oder ist leer")
            return {}

        results = {}
        for seg in self.cfg["watchlist"]:
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
            try:
                r = self.session.get(url, timeout=10)
                print(f"  [Finnhub] {ticker} → Status {r.status_code}")
                if r.status_code != 200:
                    print(f"    Fehler-Text: {r.text[:200]}")
                    continue
                data = r.json()
                if data and data.get('c'):
                    results[ticker] = data
            except Exception as e:
                print(f"  [Finnhub] Exception für {ticker}: {e}")
        return results

    # ─────────────────────────────────────────────────────────────
    # Diagnose-Modus für Tradier
    # ─────────────────────────────────────────────────────────────
    def fetch_tradier_quotes(self):
        """Tradier – mit vollem Debug"""
        api_key = os.getenv("TRADIER_KEY")
        key_len = len(api_key) if api_key else 0
        print(f"  [DEBUG] TRADIER_KEY geladen? Länge = {key_len}")

        if key_len == 0:
            print("  ❌ Tradier Key fehlt oder ist leer")
            return {}

        results = {}
        for seg in self.cfg["watchlist"]:
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            url = f"https://api.tradier.com/v1/markets/quotes?symbols={ticker}"
            headers = {"Authorization": f"Bearer {api_key}"}
            try:
                r = self.session.get(url, headers=headers, timeout=10)
                print(f"  [Tradier] {ticker} → Status {r.status_code}")
                if r.status_code != 200:
                    print(f"    Fehler-Text: {r.text[:200]}")
                    continue
                data = r.json()
                if data and 'quotes' in data and 'quote' in data['quotes']:
                    results[ticker] = data['quotes']['quote']
            except Exception as e:
                print(f"  [Tradier] Exception für {ticker}: {e}")
        return results

    # ─────────────────────────────────────────────────────────────
    # Rest (unverändert)
    # ─────────────────────────────────────────────────────────────
    def _validate_spot_prices(self, raw_data):
        spots = {}
        for seg in self.cfg.get("watchlist", {}):
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            spot = self._get_spot_price(ticker, raw_data)
            spots[ticker] = spot
        return spots

    def _get_spot_price(self, ticker, raw_data):
        print(f"  Debug spot sources for {ticker}:")

        tr = raw_data.get("tradier_quotes", {}).get(ticker, {})
        print(f"    Tradier keys: {list(tr.keys()) if tr else 'EMPTY'}")
        for key in ["last", "bid", "ask"]:
            if tr.get(key) and float(tr.get(key)) > 0:
                return float(tr.get(key))

        fh = raw_data.get("quotes", {}).get(ticker, {})
        print(f"    Finnhub keys: {list(fh.keys()) if fh else 'EMPTY'}")
        for key in ["c", "pc"]:
            if fh.get(key) and float(fh.get(key)) > 0:
                return float(fh.get(key))

        print(f"    → No valid spot price")
        return 0.0

    def fetch_cot_data(self):
        analyzer = PyCOTAnalyzer()
        cot_data = {}
        for seg in self.cfg["watchlist"]:
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            data = analyzer.get_cot_data(ticker)
            cot_data[ticker] = data
            print(f"  [COT] {ticker} → {data.get('signal_strength')} | OI-Ratio={data.get('commercial_oi_ratio')}%")
        return cot_data

    # Placeholder für die anderen Methoden (bitte deine bestehende Logik hier einsetzen)
    def fetch_options_chains(self): return {}
    def fetch_candles(self): return {}
    def fetch_eia(self): return {}
    def fetch_fred(self): return {}
    def fetch_rss(self): return {}
    def fetch_yfinance(self): return {}

    def fetch_historical_option(self, contract_symbol, period="120d"):
        try:
            df = yf.Ticker(contract_symbol).history(period=period)
            print(f"    ✅ {len(df)} days for {contract_symbol}")
            return df.to_dict("records")
        except Exception as e:
            print(f"    ⚠️ yfinance failed for {contract_symbol}: {e}")
            return []
