"""
Data Health Checker
FIX-3: Z-Score threshold 4 → 5.5 for commodity fat tails
FIX-1: Latency penalty adjusted for pre-market workflow timing
"""

import numpy as np
import datetime


class DataHealthChecker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.z_threshold = cfg["thresholds"].get("outlier_zscore_threshold", 5.5)

    def compute(self, raw_data):
        latency = self._latency_penalty(raw_data)
        completeness = self._completeness(raw_data)
        outlier, high_vol_flag = self._outlier_penalty(raw_data)

        score = (0.4 * (1 - latency) +
                 0.3 * completeness +
                 0.3 * (1 - outlier)) * 100

        warnings = []
        if latency > 0.2:
            warnings.append(f"Latency penalty: {latency:.2f}")
        if completeness < 0.8:
            warnings.append(f"Completeness low: {completeness:.2f}")
        if high_vol_flag:
            warnings.append(f"HIGH_VOLATILITY: Z-score > {self.z_threshold} detected")

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
        """
        FIX-1: Workflow runs at 06:00 UTC (08:00 CEST).
        US markets close at ~22:00 CEST = ~20:00 UTC previous day.
        Normal data age = ~10 hours. This is expected, not penalized.
        """
        now = datetime.datetime.utcnow()
        penalty = 0.0

        for key, ts_str in raw_data.get("as_of", {}).items():
            if not ts_str:
                continue
            try:
                if "T" in ts_str:
                    ts = datetime.datetime.fromisoformat(ts_str.replace("Z", ""))
                else:
                    ts = datetime.datetime.strptime(ts_str[:10], "%Y-%m-%d")
                age_hours = (now - ts).total_seconds() / 3600

                if "tradier" in key:
                    if age_hours > 18:
                        penalty = max(penalty, 0.3)
                    if age_hours > 36:
                        penalty = max(penalty, 1.0)
                else:
                    if age_hours > 120:
                        penalty = max(penalty, 0.2)
                    if age_hours > 240:
                        penalty = max(penalty, 0.5)
            except (ValueError, TypeError):
                continue

        return min(penalty, 1.0)

    def _completeness(self, raw_data):
        critical = [
            bool(raw_data.get("quotes")),
            bool(raw_data.get("options_chains")),
            bool(raw_data.get("fred", {}).get("fed_funds_rate")),
            bool(raw_data.get("cot")),
            bool(raw_data.get("rss")),
        ]
        optional = [
            bool(raw_data.get("eia")),
            bool(raw_data.get("yfinance")),
            bool(raw_data.get("candles")),
        ]
        crit_score = sum(critical) / len(critical)
        opt_score = sum(optional) / len(optional) if optional else 1.0
        return crit_score * 0.8 + opt_score * 0.2

    def _outlier_penalty(self, raw_data):
        """
        FIX-3: Z-score threshold raised to 5.5.
        Commodity markets have fat tails — legitimate breakout moves
        (e.g. +8% WTI on OPEC shock) were incorrectly flagged at Z=4.
        Z=5.5 only catches genuine data errors, not real market moves.
        """
        all_prices = []
        high_vol_flag = False

        for ticker, quote in raw_data.get("quotes", {}).items():
            price = quote.get("c", 0)
            if price and price > 0:
                all_prices.append(price)

        if len(all_prices) < 3:
            return 0.0, False

        arr = np.array(all_prices, dtype=float)
        mean = arr.mean()
        std = arr.std()
        if std == 0:
            return 0.0, False

        z_scores = np.abs((arr - mean) / std)
        flagged = np.sum(z_scores > self.z_threshold)
        penalty = min(flagged / len(arr), 1.0)

        if flagged > 0:
            high_vol_flag = True
            print(f"  HIGH_VOLATILITY_FLAG: {flagged} outlier(s) at Z>{self.z_threshold}")

        return float(penalty * 0.5), high_vol_flag
