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
        Returns (expected_value_per_contract, win_probability)
        expected_value = (mean discounted payoff - premium) * 100
        All values in USD per contract (100 shares).
        """
        if T <= 0 or sigma <= 0 or spot <= 0 or premium <= 0:
            return 0.0, 0.0

        rng = np.random.default_rng(self.seed)
        mu = r + drift * 0.20
        dt = 1 / 252
        steps = max(int(T * 252), 1)

        Z = rng.standard_normal((self.n_sims, steps))
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
        prices = spot * np.exp(log_returns.cumsum(axis=1))
        final_prices = prices[:, -1]

        # Payoff per share, discounted
        payoffs = np.maximum(final_prices - strike, 0)
        pv_payoffs = payoffs * np.exp(-r * T)

        # EV per contract = (mean payoff - premium) * 100
        mean_payoff = float(np.mean(pv_payoffs))
        ev_per_contract = (mean_payoff - premium) * 100

        # Win probability = fraction where payoff > premium
        win_prob = float(np.mean(pv_payoffs > premium))

        return round(ev_per_contract, 2), round(win_prob, 4)
