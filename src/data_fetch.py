"""
Data Fetcher – alle Quellen inkl. PyCOT v5.1 + ROBUSTER Spot-Price-Cache
"""

import datetime
import requests
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from cot.pycot_analyzer import PyCOTAnalyzer


class DataFetcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_all(self):
        raw_data = {}

        # Zuerst alle Quellen einmal holen (kein Double Fetch)
        raw_data["quotes"] = self.fetch_quotes()                # Finnhub
        raw_data["tradier_quotes"] = self.fetch_tradier_quotes()
        raw_data["candles"] = self.fetch_candles()
        raw_data["options_chains"] = self.fetch_options_chains()
        raw_data["eia"] = self.fetch_eia()
        raw_data["cot"] = self.fetch_cot_data()
        raw_data["fred"] = self.fetch_fred()
        raw_data["rss"] = self.fetch_rss()
        raw_data["yfinance"] = self.fetch_yfinance()
        raw_data["as_of"] = {"timestamp": datetime.datetime.utcnow().isoformat() + "Z"}

        # Spot-Preise aus bereits gefetchten Daten validieren
        raw_data["spot_prices"] = self._validate_all_spots(raw_data)

        return raw_data

    # ─────────────────────────────────────────────────────────────
    # ROBUSTER Spot-Price-Cache (vermeidet Double Fetch)
    # ─────────────────────────────────────────────────────────────
    def _validate_all_spots(self, raw_data):
        """Verwendet bereits gefetchte Daten aus raw_data"""
        spots = {}
        for seg in self.cfg["watchlist"]:
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            spot = self._get_spot_price_from_cache(ticker, raw_data)
            spots[ticker] = spot
            print(f"  Final spot {ticker}: ${spot:.2f}")
        return spots

    def _get_spot_price_from_cache(self, ticker, raw_data):
        """Priorität: Tradier → Finnhub → 0.0"""
        print(f"  Debug spot sources for {ticker}:")

        # 1. Tradier (bevorzugt)
        tr_quote = raw_data.get("tradier_quotes", {}).get(ticker, {})
        print(f"    Tradier quote keys: {list(tr_quote.keys()) if tr_quote else 'EMPTY'}")
        for key in ["last", "bid", "ask"]:
            price = tr_quote.get(key)
            if price and float(price) > 0:
                return float(price)

        # 2. Finnhub Fallback
        fh_quote = raw_data.get("quotes", {}).get(ticker, {})
        print(f"    Finnhub quote keys: {list(fh_quote.keys()) if fh_quote else 'EMPTY'}")
        for key in ["c", "pc"]:
            price = fh_quote.get(key)
            if price and float(price) > 0:
                return float(price)

        print(f"    → Kein gültiger Spot-Preis gefunden")
        return 0.0

    # ─────────────────────────────────────────────────────────────
    # PyCOT v5.1
    # ─────────────────────────────────────────────────────────────
    def fetch_cot_data(self):
        analyzer = PyCOTAnalyzer()
        cot_data = {}
        for seg in self.cfg["watchlist"]:
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            data = analyzer.get_cot_data(ticker)
            cot_data[ticker] = data
            print(f"  [COT] {ticker} → Index={data.get('cot_index')} | "
                  f"OI-Ratio={data.get('commercial_oi_ratio')}% | "
                  f"Strength={data.get('signal_strength')}")
        return cot_data

    # ─────────────────────────────────────────────────────────────
    # Deine bestehenden Fetch-Methoden (bitte deine aktuelle Logik hier einsetzen)
    # ─────────────────────────────────────────────────────────────
    def fetch_quotes(self):
        # Finnhub Quotes
        return {}

    def fetch_tradier_quotes(self):
        # Tradier Quotes
        return {}

    def fetch_options_chains(self):
        return {}

    def fetch_candles(self):
        return {}

    def fetch_eia(self):
        return {}

    def fetch_fred(self):
        return {}

    def fetch_rss(self):
        return {}

    def fetch_yfinance(self):
        return {}

    def fetch_historical_option(self, contract_symbol, period="120d"):
        try:
            ticker = yf.Ticker(contract_symbol)
            df = ticker.history(period=period)
            print(f"    ✅ {len(df)} days of real option prices for {contract_symbol}")
            return df.to_dict("records")
        except Exception as e:
            print(f"    ⚠️ Historical option fetch failed for {contract_symbol}: {e}")
            return []
