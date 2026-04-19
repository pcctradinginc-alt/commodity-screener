"""
PyCOT Analyzer v3 – Commercial OI-Ratio + Momentum + Signal Strength
"""

from pycot import COT

class PyCOTAnalyzer:
    def __init__(self):
        self.cot = COT()
        print("  ✅ PyCOT Analyzer v3 geladen (Commercial OI-Ratio + Momentum)")

    def get_cot_data(self, ticker: str):
        """Liefert COT-Index, Commercial OI-Ratio, Momentum und Signal-Stärke"""
        try:
            # Korrektes CFTC-Mapping
            cot_map = {
                "USO": "067411",   # Crude Oil
                "XLE": "067411",
                "CORN": "002602",  # Corn
                "SOYB": "005602",  # Soybeans
                "WEAT": "001602",  # Wheat
            }

            cot_code = cot_map.get(ticker.upper())
            if not cot_code:
                return self._default_response()

            report = self.cot.get_report(cot_code)
            if not report:
                return self._default_response()

            net_com = int(report.get("net_commercial", 0))
            total_oi = int(report.get("total_open_interest", 1)) or 1

            # Commercial Long % of Total OI
            commercial_oi_ratio = (net_com / total_oi) * 100 if net_com > 0 else 0.0

            # COT-Index (0-100)
            cot_index = max(0, min(100, 50 + (net_com / 800_000) * 50))

            # Momentum (Δ Commercial WoW)
            momentum = report.get("change_commercial", 0) / 1000.0

            # Signal Strength
            if commercial_oi_ratio > 30 and momentum > 50:
                signal_strength = "Strong Buy"
                strength_score = 2.0
            elif commercial_oi_ratio > 25:
                signal_strength = "Buy"
                strength_score = 1.5
            elif commercial_oi_ratio < -25:
                signal_strength = "Strong Sell"
                strength_score = -2.0
            else:
                signal_strength = "Neutral"
                strength_score = 1.0

            return {
                "cot_index": round(cot_index, 1),
                "commercial_oi_ratio": round(commercial_oi_ratio, 1),
                "net_commercial": net_com,
                "momentum": round(momentum, 2),
                "extrem": abs(net_com) > 400_000,
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
            "extrem": False,
            "signal_strength": "Neutral",
            "strength_score": 1.0,
            "message": "No data"
        }
