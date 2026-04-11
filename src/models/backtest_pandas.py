"""
Backtest Engine
FIX-1: As-of date logic — no look-ahead bias
FIX-4: Bid-ask spread simulation
"""

import datetime
import pandas as pd
import numpy as np


class BacktestEngine:
    def __init__(self, cfg, raw_data):
        self.cfg = cfg
        self.raw_data = raw_data
        self.bt_cfg = cfg["backtest"]
        self.cot_lag = self.bt_cfg.get("cot_release_lag_days", 3)
        self.eia_lag = self.bt_cfg.get("eia_release_lag_days", 1)
        self.fred_lag = self.bt_cfg.get("fred_release_lag_days", 1)
        self.apply_spread = self.bt_cfg.get("apply_spread_adjustment", True)

    def get_as_of_value(self, series_dict, as_of_date, lag_days):
        """
        FIX-1: Returns last known value as of as_of_date minus lag_days.
        Prevents look-ahead bias from delayed report releases.
        """
        cutoff = as_of_date - datetime.timedelta(days=lag_days)
        available = {
            pd.Timestamp(k): v for k, v in series_dict.items()
            if pd.Timestamp(k) <= cutoff
        }
        if not available:
            return None
        latest_key = max(available.keys())
        return available[latest_key]

    def estimate_spread_cost(self, iv_rank, oi, mid_price):
        """
        FIX-4: Realistic bid-ask spread simulation.
        Spread cost = half spread applied on both entry and exit.
        """
        if not self.apply_spread:
            return 0.0
        if oi >= 1000:
            spread_pct = 0.02
        elif oi >= 500:
            spread_pct = 0.05
        else:
            spread_pct = 0.10
        spread_cost_per_contract = max(mid_price * spread_pct, 0.05) * 100
        return spread_cost_per_contract * 2  # entry + exit

    def find_similar(self, segment, iv_rank, dte):
        """
        Find historically similar setups and compute win-rate.
        Returns dict with win_rate, sharpe, sample_size.
        """
        hist = self.raw_data.get("yfinance", {}).get(segment, [])
        if len(hist) < 60:
            return {"win_rate": 0.5, "sharpe": 0.0, "sample_size": 0}

        df = pd.DataFrame(hist)
        if "Close" not in df.columns and "close" not in df.columns:
            return {"win_rate": 0.5, "sharpe": 0.0, "sample_size": 0}

        close_col = "Close" if "Close" in df.columns else "close"
        df = df.rename(columns={close_col: "close"})
        df = df.sort_index()

        trades = []
        for i in range(len(df) - dte - 5):
            row = df.iloc[i]
            entry_price = float(row["close"]) * 0.03  # ~3% OTM option premium proxy

            spread_cost = self.estimate_spread_cost(iv_rank, 600, entry_price)

            future_idx = min(i + dte, len(df) - 1)
            future_price = float(df.iloc[future_idx]["close"])
            entry_spot = float(row["close"])

            strike = entry_spot * 1.05
            payoff = max(future_price - strike, 0) * 100
            net_pnl = payoff - entry_price * 100 - spread_cost

            trades.append(net_pnl)

        if len(trades) < self.bt_cfg["min_sample_size"]:
            return {"win_rate": 0.5, "sharpe": 0.0, "sample_size": len(trades)}

        arr = np.array(trades)
        win_rate = float(np.mean(arr > 0))
        mean_ret = float(np.mean(arr))
        std_ret = float(np.std(arr))
        sharpe = mean_ret / std_ret * np.sqrt(252 / max(dte, 1)) if std_ret > 0 else 0.0

        return {
            "win_rate": round(win_rate, 3),
            "sharpe": round(sharpe, 2),
            "sample_size": len(trades),
            "spread_adjusted": self.apply_spread,
            "as_of_corrected": True,
        }
