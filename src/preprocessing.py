"""
Data Health Checker – ULTRA DEBUG VERSION
Zeigt exakt, welche Quelle fehlt
"""

import numpy as np
import datetime


class DataHealthChecker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.z_threshold = cfg["thresholds"].get("outlier_zscore_threshold", 5.5)

    def compute(self, raw_data):
        print("\n=== DATA HEALTH FULL DEBUG ===")
        
        latency = self._latency_penalty(raw_data)
        completeness = self._completeness_debug(raw_data)   # ← NEU: debug-Version
        outlier, high_vol_flag = self._outlier_penalty(raw_data)

        score = (0.4 * (1 - latency) + 0.3 * completeness + 0.3 * (1 - outlier)) * 100

        print(f"→ Latency penalty     : {latency:.3f}")
        print(f"→ Completeness        : {completeness:.3f}")
        print(f"→ Outlier penalty     : {outlier:.3f}")
        print(f"→ FINAL HEALTH SCORE  : {score:.1f}/100")
        print("=============================\n")

        warnings = []
        if latency > 0.2: warnings.append(f"Latency: {latency:.2f}")
        if completeness < 0.7: warnings.append(f"Completeness low: {completeness:.2f}")
        if high_vol_flag: warnings.append(f"HIGH_VOLATILITY Z>{self.z_threshold}")

        return {
            "score": round(score, 1),
            "latency_penalty": round(latency, 3),
            "completeness": round(completeness, 3),
            "outlier_penalty": round(outlier, 3),
            "outlier_zscore_threshold": self.z_threshold,
            "high_volatility_flag": high_vol_flag,
            "warnings": warnings,
        }

    def _latency_penalty(self, raw_data):
        # bleibt unverändert (wie vorher)
        now = datetime.datetime.utcnow()
        penalty = 0.0
        for key, ts_str in raw_data.get("as_of", {}).items():
            if not ts_str: continue
            try:
                if "T" in ts_str:
                    ts = datetime.datetime.fromisoformat(ts_str.replace("Z", ""))
                else:
                    ts = datetime.datetime.strptime(ts_str[:10], "%Y-%m-%d")
                age_hours = (now - ts).total_seconds() / 3600
                if "tradier" in key:
                    if age_hours > 18: penalty = max(penalty, 0.3)
                    if age_hours > 36: penalty = max(penalty, 1.0)
                else:
                    if age_hours > 120: penalty = max(penalty, 0.2)
                    if age_hours > 240: penalty = max(penalty, 0.5)
            except:
                continue
        return min(penalty, 1.0)

    def _completeness_debug(self, raw_data):
        critical = {
            "quotes": bool(raw_data.get("quotes")),
            "options_chains": bool(raw_data.get("options_chains")),
            "fred_rate": bool(raw_data.get("fred", {}).get("fed_funds_rate")),
            "cot": bool(raw_data.get("cot")),
            "rss": bool(raw_data.get("rss")),
        }
        optional = {
            "eia": bool(raw_data.get("eia")),
            "yfinance": bool(raw_data.get("yfinance")),
            "candles": bool(raw_data.get("candles")),
            "historical_options": bool(raw_data.get("historical_options")),
        }

        print("Critical sources:")
        for k, v in critical.items():
            print(f"   {k:20} → {'✅' if v else '❌'}")
        print("Optional sources:")
        for k, v in optional.items():
            print(f"   {k:20} → {'✅' if v else '❌'}")

        crit_score = sum(critical.values()) / len(critical)
        opt_score = sum(optional.values()) / len(optional) if optional else 1.0
        total = crit_score * 0.8 + opt_score * 0.2
        return total

    def _outlier_penalty(self, raw_data):
        # bleibt unverändert
        all_prices = [quote.get("c", 0) for quote in raw_data.get("quotes", {}).values() if quote.get("c", 0) > 0]
        if len(all_prices) < 3:
            return 0.0, False
        arr = np.array(all_prices, dtype=float)
        mean, std = arr.mean(), arr.std()
        if std == 0:
            return 0.0, False
        flagged = np.sum(np.abs((arr - mean) / std) > self.z_threshold)
        penalty = min(flagged / len(arr), 1.0)
        high_vol_flag = flagged > 0
        if high_vol_flag:
            print(f"  HIGH_VOLATILITY_FLAG: {flagged} outlier(s)")
        return float(penalty * 0.5), high_vol_flag
