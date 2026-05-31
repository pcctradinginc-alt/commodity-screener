"""
Black-Scholes Fair Value + Greeks
FIX-5: Direct Tradier IV — Newton-Raphson removed
FIX-8: Volatility Surface smile correction for OTM options
"""

import numpy as np
from scipy.stats import norm


class BlackScholesCalculator:
    def __init__(self, cfg):
        self.cfg = cfg

    def smile_adjusted_iv(self, iv_atm, spot, strike, smile_factor=0.15):
        """
        FIX-8: Approximate volatility smile correction.
        OTM options have higher IV than ATM in commodity markets.
        sigma_adj = sigma_ATM * (1 + smile_factor * moneyness^2)
        """
        if spot <= 0 or strike <= 0:
            return iv_atm
        moneyness = (strike - spot) / spot
        return iv_atm * (1 + smile_factor * moneyness ** 2)

    def fair_value(self, spot, strike, r, T, sigma, option_type="call"):
        """
        FIX-5: sigma comes directly from Tradier mid_iv.
        No Newton-Raphson recalculation to avoid circular references.
        """
        if T <= 0 or sigma <= 0 or spot <= 0:
            return 0.0
        d1 = (np.log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        if option_type.lower() == "call":
            fv = spot * norm.cdf(d1) - strike * np.exp(-r * T) * norm.cdf(d2)
        else:
            fv = strike * np.exp(-r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        return max(float(fv), 0.0)

    def greeks(self, spot, strike, r, T, sigma, option_type="call"):
        if T <= 0 or sigma <= 0 or spot <= 0:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        d1 = (np.log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        gamma = norm.pdf(d1) / (spot * sigma * np.sqrt(T))
        vega = spot * norm.pdf(d1) * np.sqrt(T) / 100
        if option_type.lower() == "call":
            delta = norm.cdf(d1)
            theta = (-(spot * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                     - r * strike * np.exp(-r * T) * norm.cdf(d2)) / 365
        else:
            delta = norm.cdf(d1) - 1
            theta = (-(spot * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                     + r * strike * np.exp(-r * T) * norm.cdf(-d2)) / 365
        return {
            "delta": round(float(delta), 4),
            "gamma": round(float(gamma), 4),
            "theta": round(float(theta), 4),
            "vega": round(float(vega), 4),
        }
