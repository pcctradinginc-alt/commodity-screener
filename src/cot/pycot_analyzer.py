"""
PyCOT Analyzer v5.6 – alle Change-Spalten numeric + Momentum-Fix
"""

import cot_reports as cot
import pandas as pd
import datetime

class PyCOTAnalyzer:
    def __init__(self):
        self.current_year = datetime.datetime.now().year
        print("  ✅ PyCOT Analyzer v5.6 geladen (alle Spalten numeric)")

    def get_cot_data(self, ticker: str):
        try:
            cot_map = {
                "USO": "CRUDE OIL - NEW YORK MERCANTILE EXCHANGE",
                "XLE": "CRUDE OIL - NEW YORK MERCANTILE EXCHANGE",
                "CORN": "CORN - CHICAGO BOARD OF TRADE",
                "SOYB": "SOYBEANS - CHICAGO BOARD OF TRADE",
                "WEAT": "WHEAT-SRW - CHICAGO BOARD OF TRADE",
                "GLD": "GOLD - COMMODITY EXCHANGE INC.",
                "SLV": "SILVER - COMMODITY EXCHANGE INC.",
                "COPX": "COPPER - COMMODITY EXCHANGE INC.",
            }

            market_name = cot_map.get(ticker.upper())
            if not market_name:
                return self._default_response()

            df = cot.cot_year(self.current_year, cot_report_type="legacy_fut")
            print(f"  [COT] Downloaded {len(df)} rows for {ticker}")

            market_col = 'Market and Exchange Names'
            date_col = 'As of Date in Form YYMMDD'

            market_data = df[df[market_col].str.contains(market_name, case=False, na=False)].copy()

            if market_data.empty:
                return self._default_response()

            # ← HIER ALLE SPALTEN, DIE WIR BRAUCHEN, AUF NUMERIC ZWINGEN
            target_cols = [
                'Commercial Positions-Long (All)',
                'Commercial Positions-Short (All)',
                'Open Interest (All)',
                'Change in Commercial-Long (All)',
                'Change in Commercial-Short (All)'
            ]

            for col in target_cols:
                if col in market_data.columns:
                    market_data[col] = pd.to_numeric(market_data[col], errors='coerce').fillna(0)

            latest = market_data.sort_values(date_col, ascending=False).iloc[0]

            long_com = latest.get('Commercial Positions-Long (All)', 0)
            short_com = latest.get('Commercial Positions-Short (All)', 0)
            net_com = long_com - short_com
            total_oi = latest.get('Open Interest (All)', 1) or 1

            # Momentum mit korrekten Bindestrichen
            momentum = (latest.get('Change in Commercial-Long (All)', 0) - latest.get('Change in Commercial-Short (All)', 0)) / 1000.0

            commercial_oi_ratio = (net_com / total_oi) * 100 if net_com > 0 else 0.0

            hist_net = market_data['Commercial Positions-Long (All)'] - market_data['Commercial Positions-Short (All)']
            z_score = 0.0
            if len(hist_net) > 5 and hist_net.std() > 0:
                z_score = (net_com - hist_net.mean()) / hist_net.std()

            # Signal-Logik
            if commercial_oi_ratio > 28 and z_score > 1.5 and momentum > 40:
                signal, strength_score = "Strong Buy", 2.0
            elif commercial_oi_ratio > 22 and z_score > 1.0:
                signal, strength_score = "Buy", 1.5
            elif commercial_oi_ratio < -28 and z_score < -1.5 and momentum < -40:
                signal, strength_score = "Strong Sell", 0.5
            elif commercial_oi_ratio < -22 and z_score < -1.0:
                signal, strength_score = "Sell", 0.7
            else:
                signal, strength_score = "Neutral", 1.0

            return {
                "cot_index": round(50 + (z_score * 15), 1),
                "commercial_oi_ratio": round(commercial_oi_ratio, 1),
                "net_commercial": int(net_com),
                "momentum": round(momentum, 2),
                "z_score": round(z_score, 2),
                "signal_strength": signal,
                "strength_score": strength_score,
            }

        except Exception as e:
            print(f"  ❌ PyCOT v5.6 Error für {ticker}: {e}")
            return self._default_response()

    def _default_response(self):
        return {
            "cot_index": 50.0,
            "commercial_oi_ratio": 0.0,
            "net_commercial": 0,
            "momentum": 0.0,
            "z_score": 0.0,
            "signal_strength": "Neutral",
            "strength_score": 1.0
        }
