"""
Backtest Engine v2 — Rolling-Window auf Underlying-Preisbewegung (nicht Option-Preis)
Win = underlying move deckt Prämie bei Expiry (breakeven-adjusted)
"""

import pandas as pd
import numpy as np


class BacktestPandas:
    def find_similar_real(self, candidate: dict):
        """
        Simulates historical win rate by asking: how often did the underlying
        move enough (past breakeven) within DTE trading days?

        Uses underlying_history (ETF price data from yfinance), not option price data.
        """
        spot     = candidate.get("spot", 0)
        strike   = candidate.get("strike", 0)
        dte      = int(candidate.get("dte", 30))
        opt_type = candidate.get("option_type", "call").lower()
        premium  = candidate.get("mid_price", 0)

        if spot <= 0 or strike <= 0 or premium <= 0 or dte < 5:
            return {"win_rate": 0.48, "n": 0}

        # Prefer underlying history over option history
        underlying = candidate.get("underlying_history", []) or candidate.get("historical_data", [])
        if not underlying or len(underlying) < dte + 10:
            return {"win_rate": 0.48, "n": 0}

        try:
            df = pd.DataFrame(underlying)

            # Normalize close column
            close_col = None
            for c in ["Close", "close", "Adj Close"]:
                if c in df.columns:
                    close_col = c
                    break
            if close_col is None:
                df = df.reset_index()
                for c in df.columns:
                    if "close" in str(c).lower():
                        close_col = c
                        break

            if close_col is None:
                return {"win_rate": 0.48, "n": 0}

            closes = df[close_col].dropna().astype(float).values
            n_total = len(closes)

            if n_total < dte + 5:
                return {"win_rate": 0.48, "n": 0}

            wins = 0
            n_samples = 0

            # Rolling window: enter at each historical point, exit dte days later
            for i in range(n_total - dte):
                entry_spot = closes[i]
                exit_spot  = closes[i + dte]
                if entry_spot <= 0:
                    continue

                # Scale strike to same moneyness ratio as current setup
                moneyness  = strike / spot
                adj_strike = entry_spot * moneyness

                # Breakeven = strike ± premium (scaled by spot ratio)
                premium_scaled = premium * (entry_spot / spot) if spot > 0 else premium

                if opt_type == "call":
                    breakeven  = adj_strike + premium_scaled
                    profitable = exit_spot > breakeven
                else:
                    breakeven  = adj_strike - premium_scaled
                    profitable = exit_spot < breakeven

                wins      += int(profitable)
                n_samples += 1

            win_rate = wins / n_samples if n_samples > 0 else 0.48
            return {"win_rate": round(win_rate, 3), "n": n_samples}

        except Exception as e:
            print(f"    ⚠️ Backtest error: {e}")
            return {"win_rate": 0.48, "n": 0}
