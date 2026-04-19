"""
PyCOT Analyzer v5.1 – using cot-reports (stabil & zuverlässig)
"""

import cot_reports as cot
import pandas as pd
import os
import json
import statistics

class PyCOTAnalyzer:
    def __init__(self):
        self.history_file = os.path.join("data", "cot_history.json")
        self.current_year = datetime.datetime.now().year
        print("  ✅ PyCOT Analyzer v5.1 geladen (using cot-reports)")

    def get_cot_data(self, ticker: str):
        try:
            # Korrekte Markt-Namen für cot-reports
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

            # COT-Daten für das aktuelle Jahr laden
            df = cot.get_reports(self.current_year, "legacy_fut")

            # Filtern auf den Markt
            market_data = df[df['Market_and_Exchange_Names'] == market_name]
            if market_data.empty:
                return self._default_response()

            # Neuesten Report nehmen
            latest = market_data.sort_values('As_of_Date_In_Form_YYMMDD', ascending=False).iloc[0]

            long_com = latest['Comm_Positions_Long_All']
            short_com = latest['Comm_Positions_Short_All']
            net_com = long_com - short_com
            total_oi = latest['Open_Interest_All']

            # Momentum (Veränderung)
            momentum = (latest['Change_in_Comm_Long_All'] - latest['Change_in_Comm_Short_All']) / 1000.0

            # OI-Ratio
            commercial_oi_ratio = (net_com / total_oi) * 100 if net_com > 0 else 0.0

            # Z-Score über alle verfügbaren Daten des Jahres
            hist_net = market_data['Comm_Positions_Long_All'] - market_data['Comm_Positions_Short_All']
            z_score = 0.0
            if len(hist_net) > 5:
                mean = hist_net.mean()
                std = hist_net.std() if hist_net.std() > 0 else 1.0
                z_score = (net_com - mean) / std

            # Signal Strength
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
                "message": "OK"
            }

        except Exception as e:
            print(f"  PyCOT error for {ticker}: {e}")
            return self._default_response()

    def _default_response(self):
        return {
            "cot_index": 50.0,
            "commercial_oi_ratio": 0.0,
            "net_commercial": 0,
            "momentum": 0.0,
            "z_score": 0.0,
            "signal_strength": "Neutral",
            "strength_score": 1.0,
            "message": "No Data"
        }
