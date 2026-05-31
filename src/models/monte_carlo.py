"""
Monte Carlo Simulator — GBM, vectorized
FIX: Correct PUT/CALL payoff formula
FIX: option_type parameter added
"""

import numpy as np


class MonteCarloSimulator:
    def __init__(self, cfg):
        self.n_sims = cfg["monte_carlo"]["simulations"]
        self.seed   = cfg["monte_carlo"]["seed"]

    def simulate(self, spot, strike, r, T, sigma, premium,
                 drift=0.0, option_type="call"):
        """
        Returns (expected_value_per_contract_usd, win_probability)

        option_type: "call" or "put"
        EV = (mean discounted payoff - premium) * 100  [USD per contract]
        Positive EV = statistically profitable at this premium.
        """
        if T <= 0 or sigma <= 0 or spot <= 0 or premium <= 0:
            return 0.0, 0.0

        rng   = np.random.default_rng(self.seed)
        mu    = r + drift * 0.20   # Prophet drift, 20% weight
        dt    = 1 / 252
        steps = max(int(T * 252), 1)

        # Vectorized GBM: (n_sims × steps)
        Z           = rng.standard_normal((self.n_sims, steps))
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
        prices      = spot * np.exp(log_returns.cumsum(axis=1))
        final       = prices[:, -1]

        # Correct payoff per option type
        if option_type.lower() == "put":
            payoffs = np.maximum(strike - final, 0)
        else:
            payoffs = np.maximum(final - strike, 0)

        pv          = payoffs * np.exp(-r * T)
        mean_payoff = float(pv.mean())

        # EV per contract (100 shares)
        ev       = (mean_payoff - premium) * 100
        win_prob = float((pv > premium).mean())

        return round(ev, 2), round(win_prob, 4)
