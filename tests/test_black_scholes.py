"""Tests for Black-Scholes fair value, Greeks and smile fallback."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from models.black_scholes import BlackScholesCalculator

BS = BlackScholesCalculator({})
S, K, r, T = 100.0, 100.0, 0.05, 1.0   # ATM, 1 year, 5% rate
SIGMA = 0.20


# --- Fair value ---

def test_call_positive():
    assert BS.fair_value(S, K, r, T, SIGMA, "call") > 0

def test_put_positive():
    assert BS.fair_value(S, K, r, T, SIGMA, "put") > 0

def test_put_call_parity():
    c = BS.fair_value(S, K, r, T, SIGMA, "call")
    p = BS.fair_value(S, K, r, T, SIGMA, "put")
    # C - P = S - K*e^(-rT)
    expected = S - K * (2.718281828 ** (-r * T))
    assert abs((c - p) - expected) < 0.01

def test_deep_itm_call_near_intrinsic():
    # S=150, K=100, T=0.01 → fair value ≈ intrinsic (50)
    fv = BS.fair_value(150, 100, r, 0.01, SIGMA, "call")
    assert fv > 49.0

def test_deep_otm_call_near_zero():
    fv = BS.fair_value(50, 100, r, 0.01, SIGMA, "call")
    assert fv < 0.01

def test_dte_zero_returns_zero():
    assert BS.fair_value(S, K, r, 0.0, SIGMA, "call") == 0.0
    assert BS.fair_value(S, K, r, 0.0, SIGMA, "put") == 0.0

def test_zero_sigma_returns_zero():
    assert BS.fair_value(S, K, r, T, 0.0, "call") == 0.0

def test_zero_spot_returns_zero():
    assert BS.fair_value(0, K, r, T, SIGMA, "call") == 0.0


# --- Greeks ---

def test_call_delta_in_bounds():
    g = BS.greeks(S, K, r, T, SIGMA, "call")
    assert 0 < g["delta"] < 1

def test_put_delta_in_bounds():
    g = BS.greeks(S, K, r, T, SIGMA, "put")
    assert -1 < g["delta"] < 0

def test_atm_call_delta_near_half():
    g = BS.greeks(S, K, r, T, SIGMA, "call")
    assert 0.45 < g["delta"] < 0.65

def test_gamma_positive():
    assert BS.greeks(S, K, r, T, SIGMA, "call")["gamma"] > 0

def test_vega_positive():
    assert BS.greeks(S, K, r, T, SIGMA, "call")["vega"] > 0

def test_theta_negative():
    assert BS.greeks(S, K, r, T, SIGMA, "call")["theta"] < 0
    assert BS.greeks(S, K, r, T, SIGMA, "put")["theta"] < 0

def test_greeks_zero_T_returns_zeros():
    g = BS.greeks(S, K, r, 0.0, SIGMA, "call")
    assert g == {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}


# --- Smile fallback ---

def test_smile_otm_higher_than_atm():
    iv_atm = 0.20
    sigma_otm = BS.smile_adjusted_iv(iv_atm, 100, 110, smile_factor=0.15)
    assert sigma_otm > iv_atm

def test_smile_itm_higher_than_atm():
    iv_atm = 0.20
    sigma_itm = BS.smile_adjusted_iv(iv_atm, 100, 90, smile_factor=0.15)
    assert sigma_itm > iv_atm

def test_smile_atm_unchanged():
    iv_atm = 0.20
    sigma = BS.smile_adjusted_iv(iv_atm, 100, 100, smile_factor=0.15)
    assert sigma == iv_atm

def test_smile_zero_spot_returns_iv_atm():
    assert BS.smile_adjusted_iv(0.20, 0, 100) == 0.20
