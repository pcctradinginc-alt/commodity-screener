"""Tests for rule-based conviction scoring in ClaudeDeepAnalysis."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from analysis.claude_deep_analysis import compute_conviction


def _c(**kwargs):
    """Build a minimal candidate dict with sensible defaults."""
    defaults = {
        "mc_ev": 0, "mc_win_prob": 0.48,
        "hist_win_rate": 0.48, "hist_sample_size": 0,
        "cot_z": 0.0, "edge_score": 0,
    }
    defaults.update(kwargs)
    return defaults


# --- Bounds ---

def test_result_is_int():
    assert isinstance(compute_conviction(_c()), int)

def test_minimum_is_one():
    assert compute_conviction(_c()) >= 1

def test_maximum_is_nine():
    assert compute_conviction(_c(
        mc_ev=200, mc_win_prob=0.9,
        hist_win_rate=0.9, hist_sample_size=100,
        cot_z=3.0, edge_score=50,
    )) <= 9


# --- Individual signal contributions ---

def test_high_mc_ev_increases_conviction():
    low  = compute_conviction(_c(mc_ev=3))
    high = compute_conviction(_c(mc_ev=60))
    assert high > low

def test_high_win_prob_increases_conviction():
    low  = compute_conviction(_c(mc_win_prob=0.48))
    high = compute_conviction(_c(mc_win_prob=0.60))
    assert high > low

def test_hist_win_rate_ignored_below_min_samples():
    with_hist    = compute_conviction(_c(hist_win_rate=0.60, hist_sample_size=30))
    without_hist = compute_conviction(_c(hist_win_rate=0.60, hist_sample_size=10))
    assert with_hist > without_hist

def test_strong_cot_increases_conviction():
    weak   = compute_conviction(_c(cot_z=0.0))
    strong = compute_conviction(_c(cot_z=2.0))
    assert strong > weak

def test_high_edge_score_increases_conviction():
    # Use a base signal (mc_ev=8 → 1pt) so the edge_score point is distinguishable
    low  = compute_conviction(_c(mc_ev=8, edge_score=10))
    high = compute_conviction(_c(mc_ev=8, edge_score=35))
    assert high > low


# --- Representative setups ---

def test_all_signals_max_gives_nine():
    assert compute_conviction(_c(
        mc_ev=100, mc_win_prob=0.60,
        hist_win_rate=0.60, hist_sample_size=50,
        cot_z=2.0, edge_score=40,
    )) == 9

def test_no_signals_gives_one():
    assert compute_conviction(_c()) == 1

def test_moderate_setup_mid_range():
    score = compute_conviction(_c(
        mc_ev=12, mc_win_prob=0.51,
        hist_win_rate=0.51, hist_sample_size=35,
        cot_z=0.8, edge_score=20,
    ))
    assert 3 <= score <= 6
