"""Tests for Monte Carlo simulator: EV, win_prob, cost model, reproducibility."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from models.monte_carlo import MonteCarloSimulator

CFG = {
    "monte_carlo": {"simulations": 5000, "seed": 42, "contract_multiplier": 100},
    "thresholds":  {"commission_per_contract": 0.65},
}
MC = MonteCarloSimulator(CFG)
S, K, r, T, SIGMA = 100.0, 100.0, 0.05, 0.25, 0.20  # ATM, 3 months


# --- Basic sanity ---

def test_returns_tuple():
    result = MC.simulate(S, K, r, T, SIGMA, premium=3.0)
    assert isinstance(result, tuple) and len(result) == 2

def test_win_prob_in_bounds():
    _, wp = MC.simulate(S, K, r, T, SIGMA, premium=3.0)
    assert 0.0 <= wp <= 1.0

def test_invalid_inputs_return_zero():
    assert MC.simulate(0, K, r, T, SIGMA, 3.0) == (0.0, 0.0)
    assert MC.simulate(S, K, r, 0, SIGMA, 3.0) == (0.0, 0.0)
    assert MC.simulate(S, K, r, T, 0, 3.0)    == (0.0, 0.0)
    assert MC.simulate(S, K, r, T, SIGMA, 0)  == (0.0, 0.0)


# --- Reproducibility ---

def test_seed_reproducibility():
    ev1, wp1 = MC.simulate(S, K, r, T, SIGMA, premium=3.0)
    ev2, wp2 = MC.simulate(S, K, r, T, SIGMA, premium=3.0)
    assert ev1 == ev2 and wp1 == wp2


# --- Direction ---

def test_deep_itm_call_positive_ev():
    # S=100, K=70, cheap premium → EV should be positive
    ev, _ = MC.simulate(100, 70, r, T, SIGMA, premium=0.50)
    assert ev > 0

def test_deep_otm_call_negative_ev():
    # S=100, K=140, expensive premium relative to tiny probability
    ev, _ = MC.simulate(100, 140, r, T, SIGMA, premium=2.00)
    assert ev < 0

def test_put_direction():
    # Deep ITM put (S=70, K=100) with cheap premium → positive EV
    ev, _ = MC.simulate(70, 100, r, T, SIGMA, premium=0.50, option_type="put")
    assert ev > 0


# --- Cost model ---

def test_commission_reduces_ev():
    cfg_no_comm = {
        "monte_carlo": {"simulations": 5000, "seed": 42, "contract_multiplier": 100},
        "thresholds":  {"commission_per_contract": 0.0},
    }
    mc_no = MonteCarloSimulator(cfg_no_comm)
    ev_with, _ = MC.simulate(S, K, r, T, SIGMA, premium=3.0)
    ev_without, _ = mc_no.simulate(S, K, r, T, SIGMA, premium=3.0)
    assert abs((ev_without - ev_with) - 0.65) < 0.01

def test_ask_used_when_higher_than_mid():
    # ask=4.0 > mid=3.0 → entry cost is 4.0 → lower EV
    ev_mid, _ = MC.simulate(S, K, r, T, SIGMA, premium=3.0, ask=None)
    ev_ask, _ = MC.simulate(S, K, r, T, SIGMA, premium=3.0, ask=4.0)
    assert ev_ask < ev_mid

def test_ask_below_mid_ignored():
    # ask=2.0 < mid=3.0 → nonsensical ask, falls back to mid
    ev_mid, _ = MC.simulate(S, K, r, T, SIGMA, premium=3.0, ask=None)
    ev_bad,  _ = MC.simulate(S, K, r, T, SIGMA, premium=3.0, ask=2.0)
    assert ev_mid == ev_bad
