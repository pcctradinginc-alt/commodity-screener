"""
PyCOT Analyzer v4 – Commercial OI-Ratio + historischer Z-Score + Momentum + korrektes Short-Signal
"""

from pycot import COT
import statistics

class PyCOTAnalyzer:
    def __init__(self):
        self.cot = COT()
        self.history_cache = {}   # für Z-Score-Berechnung
        print("  ✅ PyCOT Analyzer v4 geladen (OI-Ratio + Z-Score + korrektes Mapping)")

    def get_cot_data(self, ticker: str):
        try:
            # Erweitertes, korrektes CFTC-Mapping
            cot_map = {
                "USO": "067411",   # Crude Oil
                "XLE": "067411",
                "CORN": "002602",  # Corn
                "SOYB": "005602",  # Soybeans
                "WEAT": "001602",  # Wheat
                "GLD": "088691",   # Gold
                "SLV": "084691",   # Silver
                "COPX": "085692",  # Copper
            }

            cot_code = cot_map.get(ticker.upper())
            if not cot_code:
                return self._default_response(ticker)

            report = self.cot.get_report(cot_code)
            if not report:
                return self._default_response(ticker)

            net_com = int(report.get("net_commercial", 0))
            total_oi = int(report.get("total_open_interest", 1)) or 1

            # Commercial OI-Ratio (Anteil am Gesamt-Open-Interest)
            commercial_oi_ratio = (net_com / total_oi) * 100 if net_com > 0 else 0.0

            # Momentum (Δ Commercial WoW)
            momentum = report.get("change_commercial", 0) / 1000.0

            # Historischer Z-Score (Vergleich mit eigenem 3-Jahres-Durchschnitt)
            z_score = self._calculate_z_score(cot_code, net_com)

            # Signal Strength – jetzt mit historischer Normierung
            if commercial_oi_ratio > 28 and z_score > 1.5 and momentum > 40:
                signal_strength = "Strong Buy"
                strength_score = 2.0
            elif commercial_oi_ratio > 22 and z_score > 1.0:
                signal_strength = "Buy"
                strength_score = 1.5
            elif commercial_oi_ratio < -28 and z_score < -1.5 and momentum < -40:
                signal_strength = "Strong Sell"
                strength_score = 0.5
            elif commercial_oi_ratio < -22 and z_score < -1.0:
                signal_strength = "Sell"
                strength_score = 0.7
            else:
                signal_strength = "Neutral"
                strength_score = 1.0

            return {
                "cot_index": round(50 + (net_com / 800_000) * 50, 1),
                "commercial_oi_ratio": round(commercial_oi_ratio, 1),
                "net_commercial": net_com,
                "momentum": round(momentum, 2),
                "z_score": round(z_score, 2),
                "extrem": abs(z_score) > 2.0,
                "signal_strength": signal_strength,
                "strength_score": strength_score,
                "message": "OK"
            }

        except Exception as e:
            print(f"  PyCOT error for {ticker}: {e}")
            return self._default_response(ticker)

    def _calculate_z_score(self, cot_code: str, current_net: int):
        """Historischer Z-Score der Commercial Net Position"""
        if cot_code not in self.history_cache:
            self.history_cache[cot_code] = []
        
        self.history_cache[cot_code].append(current_net)
        # Behalte nur die letzten 156 Wochen (~3 Jahre)
        if len(self.history_cache[cot_code]) > 156:
            self.history_cache[cot_code] = self.history_cache[cot_code][-156:]

        hist = self.history_cache[cot_code]
        if len(hist) < 20:
            return 0.0

        mean = statistics.mean(hist)
        std = statistics.stdev(hist) if len(hist) > 1 else 1
        return (current_net - mean) / std

    def _default_response(self, ticker=""):
        return {
            "cot_index": 50.0,
            "commercial_oi_ratio": 0.0,
            "net_commercial": 0,
            "momentum": 0.0,
            "z_score": 0.0,
            "extrem": False,
            "signal_strength": "Neutral",
            "strength_score": 1.0,
            "message": f"No data for {ticker}"
        }
