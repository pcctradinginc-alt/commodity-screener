"""
Data Fetcher – alle Quellen inkl. PyCOT v3 (Commercial OI-Ratio + Momentum)
"""

import datetime
import requests
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from cot.pycot_analyzer import PyCOTAnalyzer   # ← NEU: PyCOT Integration


class DataFetcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_all(self):
        """Hauptmethode – holt alle Daten und integriert PyCOT"""
        raw_data = {}

        # Basis-Daten
        raw_data["quotes"] = self.fetch_quotes()
        raw_data["candles"] = self.fetch_candles()
        raw_data["options_chains"] = self.fetch_options_chains()
        raw_data["tradier_quotes"] = self.fetch_tradier_quotes()
        raw_data["eia"] = self.fetch_eia()
        raw_data["cot"] = self.fetch_cot_data()           # ← NEU: PyCOT
        raw_data["fred"] = self.fetch_fred()
        raw_data["rss"] = self.fetch_rss()
        raw_data["yfinance"] = self.fetch_yfinance()
        raw_data["as_of"] = {"timestamp": datetime.datetime.utcnow().isoformat() + "Z"}

        print("  ✅ PyCOT Daten integriert")
        return raw_data

    # ─────────────────────────────────────────────────────────────
    # PyCOT Integration (neu)
    # ─────────────────────────────────────────────────────────────
    def fetch_cot_data(self):
        """PyCOT-Daten für alle relevanten Ticker holen"""
        analyzer = PyCOTAnalyzer()
        cot_data = {}

        for seg in self.cfg["watchlist"]:
            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            data = analyzer.get_cot_data(ticker)
            cot_data[ticker] = data
            print(f"  [COT] {ticker} → Index={data['cot_index']}% | "
                  f"OI-Ratio={data['commercial_oi_ratio']}% | "
                  f"Strength={data['signal_strength']}")

        return cot_data

    # ─────────────────────────────────────────────────────────────
    # Bestehende Fetch-Methoden (unverändert)
    # ─────────────────────────────────────────────────────────────
    def fetch_quotes(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_candles(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_options_chains(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_tradier_quotes(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_eia(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_fred(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_rss(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_yfinance(self):
        # ... deine bestehende Implementierung ...
        return {}

    def fetch_historical_option(self, contract_symbol, period="120d"):
        """Yfinance historische Optionsdaten"""
        try:
            ticker = yf.Ticker(contract_symbol)
            df = ticker.history(period=period)
            print(f"    ✅ {len(df)} days of real option prices for {contract_symbol}")
            return df.to_dict("records")
        except Exception as e:
            print(f"    ⚠️  Historical option fetch failed for {contract_symbol}: {e}")
            return []

    # Weitere Methoden (falls vorhanden) bleiben unverändert
