"""
PyCOT Analyzer v5 – Persistente Historie + Z-Score + OI-Ratio + Momentum
"""

from pycot import COT
import json
import os
import statistics
import datetime

class PyCOTAnalyzer:
    def __init__(self):
        self.cot = COT()
        self.history_file = os.path.join("data", "cot_history.json")
        self.history = self._load_history()
        print("  ✅ PyCOT Analyzer v5 geladen (persistente Historie + Z-Score)")

    def _load_history(self):
        """Lädt gespeicherte COT-Historie oder erstellt neue"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file) as f:
                    return json.load(f)
            except:
                pass
        return {}  # {cot_code: [net_com_values]}

    def _save_history(self):
        """Speichert Historie für nächsten Run"""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w") as f:
            json.dump(self.history, f, indent=2)

    def get_cot_data(self, ticker: str):
        try:
            # Erweitertes Mapping
            cot_map = {
                "USO": "067411", "XLE": "067411",
                "CORN": "002602", "SOYB": "005602", "WEAT": "001602",
                "GLD": "088691", "SLV": "084691", "COPX": "085692",
            }

            cot_code = cot_map.get(ticker.upper())
            if not cot_code:
                return self._default_response()

            report = self.cot.get_report(cot_code)
            if not report:
                return self._default_response()

            net_com = int(report.get("net_commercial", 0))
            total_oi = int(report.get("total_open_interest", 1)) or 1
            momentum = report.get("change_commercial", 0) / 1000.0

            # OI-Ratio
            commercial_oi_ratio = (net_com / total_oi) * 100 if net_com > 0 else 0.0

            # Historie pflegen
            if cot_code not in self.history:
                self.history[cot_code] = []
            self.history[cot_code].append(net_com)
            # Nur letzte 156 Wochen (~3 Jahre) behalten
            if len(self.history[cot_code]) > 156:
                self.history[cot_code] = self.history[cot_code][-156:]

            self._save_history()

            # Z-Score
            hist = self.history[cot_code]
            z_score = 0.0
            if len(hist) >= 20:
                mean = statistics.mean(hist)
                std = statistics.stdev(hist) if len(hist) > 1 else 1.0
                z_score = (net_com - mean) / std

            # Signal Strength (verbessert)
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
            return self._default_response()

    def _default_response(self):
        return {
            "cot_index": 50.0,
            "commercial_oi_ratio": 0.0,
            "net_commercial": 0,
            "momentum": 0.0,
            "z_score": 0.0,
            "extrem": False,
            "signal_strength": "Neutral",
            "strength_score": 1.0,
            "message": "No data"
        }
