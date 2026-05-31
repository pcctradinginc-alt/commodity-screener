"""Tests for BacktestPandas rolling-window win-rate engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from models.backtest_pandas import BacktestPandas

BT = BacktestPandas()


def _history(prices):
    return [{"Close": p} for p in prices]

def _candidate(prices, opt_type="call", premium=1.0, spot=100.0, strike=102.0, dte=5):
    return {
        "spot": spot, "strike": strike, "dte": dte,
        "option_type": opt_type, "mid_price": premium,
        "spread_pct": 0.05,
        "underlying_history": _history(prices),
    }


# --- Fallback cases ---

def test_too_few_samples_returns_neutral():
    # 20 prices, dte=5 → 15 samples < 30 → default
    prices = [100.0 + i * 0.1 for i in range(20)]
    result = BT.find_similar_real(_candidate(prices))
    assert result["win_rate"] == 0.48

def test_too_short_history_returns_neutral():
    # history shorter than dte+5
    prices = [100.0] * 8
    result = BT.find_similar_real(_candidate(prices, dte=5))
    assert result["win_rate"] == 0.48
    assert result["n"] == 0

def test_zero_spot_returns_neutral():
    result = BT.find_similar_real(_candidate([100.0] * 50, spot=0))
    assert result["win_rate"] == 0.48

def test_zero_premium_returns_neutral():
    result = BT.find_similar_real(_candidate([100.0] * 50, premium=0))
    assert result["win_rate"] == 0.48


# --- Direction correctness ---

def test_strongly_rising_prices_call_wins():
    # Prices rise sharply: 100 → 150 over 50 steps, dte=5
    # premium=0.05 (tiny) so breakeven is very close to adj_strike
    prices = [100.0 + i * 1.0 for i in range(50)]
    result = BT.find_similar_real(_candidate(
        prices, opt_type="call", spot=100.0, strike=101.0, dte=5, premium=0.05
    ))
    assert result["n"] >= 30
    assert result["win_rate"] > 0.50

def test_strongly_falling_prices_put_wins():
    # Prices fall: 150 → 100 over 50 steps, tiny premium so breakeven easily reached
    prices = [150.0 - i * 1.0 for i in range(50)]
    result = BT.find_similar_real(_candidate(
        prices, opt_type="put", spot=150.0, strike=149.0, dte=5, premium=0.05
    ))
    assert result["n"] >= 30
    assert result["win_rate"] > 0.50

def test_flat_prices_call_loses():
    # Flat prices → call above current price never reaches breakeven
    prices = [100.0] * 50
    result = BT.find_similar_real(_candidate(
        prices, opt_type="call", spot=100.0, strike=105.0, dte=5, premium=0.50
    ))
    assert result["n"] >= 30
    assert result["win_rate"] < 0.20

def test_zero_premium_call_always_wins():
    # premium=0 → breakeven = strike → any price above strike wins
    prices = [100.0 + i * 0.3 for i in range(50)]
    result = BT.find_similar_real(_candidate(
        prices, opt_type="call", spot=100.0, strike=95.0, dte=5, premium=0.0
    ))
    # premium=0 triggers neutral fallback
    assert result["win_rate"] == 0.48


# --- Sample count ---

def test_n_reported_correctly():
    prices = [100.0 + i * 0.1 for i in range(50)]
    result = BT.find_similar_real(_candidate(prices, dte=5))
    assert result["n"] == 50 - 5   # n_total - dte
