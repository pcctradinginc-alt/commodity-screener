"""
Monte Carlo Simulator — GBM, 10,000 simulations
"""

import numpy as np


class MonteCarloSimulator:
    def __init__(self, cfg):
        self.n_sims = cfg["monte_carlo"]["simulations"]
        self.seed = cfg["monte_carlo"]["seed"]

    def simulate(self, spot, strike, r, T, sigma, premium, drift=0.0):
        """
        Returns (expected_value, win_probability)
        drift from Prophet (weight 20% per architecture doc)
        """
        if T <= 0 or sigma <= 0 or spot <= 0:
            return -premium * 100, 0.0

        rng = np.random.default_rng(self.seed)
        mu = r + drift * 0.20  # Prophet drift weighted at 20%
        dt = 1 / 252
        steps = max(int(T * 252), 1)

        Z = rng.standard_normal((self.n_sims, steps))
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
        prices = spot * np.exp(log_returns.cumsum(axis=1))
        final_prices = prices[:, -1]

        payoffs = np.maximum(final_prices - strike, 0)
        pv_payoffs = payoffs * np.exp(-r * T)
        ev = float(np.mean(pv_payoffs) - premium) * 100
        win_prob = float(np.mean(pv_payoffs > 0))

        return round(ev, 2), round(win_prob, 4)
