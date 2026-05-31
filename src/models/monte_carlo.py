"""
Monte Carlo Simulator — GBM, vectorized

sigma = HV (realized vol), not market IV.
Positive EV = option statistically cheap relative to expected realized moves.
EV is net of entry cost (ask fill) and commission.
"""

import numpy as np


class MonteCarloSimulator:
    def __init__(self, cfg):
        self.n_sims     = cfg["monte_carlo"]["simulations"]
        self.seed       = cfg["monte_carlo"]["seed"]
        self.multiplier = cfg.get("monte_carlo", {}).get("contract_multiplier", 100)
        thr = cfg.get("thresholds", {})
        self.commission = float(thr.get("commission_per_contract", 0.65))

    def simulate(self, spot, strike, r, T, sigma, premium,
                 drift=0.0, option_type="call", ask=None):
        """
        Returns (net_expected_value_usd, win_probability)

        net_ev = (mean_discounted_payoff - entry_cost) * multiplier - commission
        entry_cost: ask price if available, else mid (premium).
        win_prob: fraction of paths where discounted payoff > entry_cost.
        """
        if T <= 0 or sigma <= 0 or spot <= 0 or premium <= 0:
            return 0.0, 0.0

        # Entry at ask (realistic fill); fall back to mid when ask unavailable
        entry_cost = float(ask) if ask and ask > premium else premium

        rng   = np.random.default_rng(self.seed)
        mu    = r + drift * 0.20   # Prophet drift, 20% weight
        dt    = 1 / 252
        steps = max(int(T * 252), 1)

        Z           = rng.standard_normal((self.n_sims, steps))
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
        prices      = spot * np.exp(log_returns.cumsum(axis=1))
        final       = prices[:, -1]

        if option_type.lower() == "put":
            payoffs = np.maximum(strike - final, 0)
        else:
            payoffs = np.maximum(final - strike, 0)

        pv          = payoffs * np.exp(-r * T)
        mean_payoff = float(pv.mean())

        # Net EV: gross P&L minus entry-cost shortfall minus commission
        ev       = (mean_payoff - entry_cost) * self.multiplier - self.commission
        win_prob = float((pv > entry_cost).mean())

        return round(ev, 2), round(win_prob, 4)
