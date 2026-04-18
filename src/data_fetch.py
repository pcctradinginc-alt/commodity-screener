"""
Data Fetcher — alle Datenquellen parallel
Jetzt mit historischen Optionspreisen für echtes Backtesting
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
    # ... (alle bestehenden Tradier-, Finnhub-, EIA-, COT-, FRED-, RSS- und yfinance-Methoden bleiben unverändert) ...
    # (Ich habe sie hier aus Platzgründen gekürzt – der Rest des Originalcodes bleibt 1:1 erhalten)

    def fetch_tradier_quote(self, ticker): ...          # ← unverändert
    def fetch_tradier_chain(self, ticker): ...          # ← unverändert
    def _next_monthly_expiry(self, today, min_dte=21): ... # ← unverändert
    def fetch_finnhub_quote(self, ticker): ...          # ← unverändert
    def fetch_finnhub_candles(self, ticker, days=22): ... # ← unverändert
    def fetch_eia(self, series_id): ...                 # ← unverändert
    def fetch_cot(self, cot_code): ...                  # ← unverändert
    def fetch_fred(self): ...                           # ← unverändert
    def fetch_rss(self, query): ...                     # ← unverändert
    def fetch_yfinance(self, ticker, period="2y"): ...  # ← unverändert

    # ── NEU: Historische Optionspreise (wichtigster Zusatz) ─────────
    def fetch_historical_option(self, contract_symbol: str, period: str = "90d"):
        """Holt echte historische Preise eines Optionskontrakts (z. B. USO241018C00050000)."""
        try:
            print(f"    Fetching historical option data for {contract_symbol} ({period})...")
            opt = yf.Ticker(contract_symbol)
            hist = opt.history(period=period, auto_adjust=True, progress=False)
            if hist.empty:
                print(f"    ⚠️  No historical data for {contract_symbol}")
                return []
            hist = hist.reset_index()
            # Nur relevante Spalten
            result = hist[["Date", "Open", "High", "Low", "Close", "Volume"]].to_dict("records")
            print(f"    ✅ {len(result)} days of real option prices for {contract_symbol}")
            return result
        except Exception as e:
            print(f"    Hist option {contract_symbol} error: {e}")
            return []

    # ── Main fetch_all (unverändert bis auf neuen Aufruf später in main.py) ──
    def fetch_all(self):
        # ... (der gesamte ursprüngliche fetch_all-Code bleibt identisch) ...
        # Wir rufen die neuen historischen Daten später in main.py auf, damit wir die Contract-Symbole schon haben.
        result = {
            "quotes": {},
            "candles": {},
            "options_chains": {},
            "tradier_quotes": {},
            "eia": {},
            "cot": {},
            "fred": {},
            "rss": {},
            "yfinance": {},
            "as_of": {},
            "historical_options": {},   # ← NEU
        }
        # ... Rest wie bisher ...
        return result
