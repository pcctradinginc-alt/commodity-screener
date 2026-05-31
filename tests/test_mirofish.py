"""Tests for MirofishChecker three-gate filter."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from analysis.mirofish_check import MirofishChecker

CFG = {"thresholds": {"mirofish_score_min": 18}}
MF  = MirofishChecker(CFG)


def _c(**kwargs):
    """Candidate that passes all gates by default."""
    base = {
        "mc_ev": 25.0, "bs_edge": 0.01, "edge_score": 20,
        "iv_premium": 0.2,
        "cot_z": 1.0, "cot_proxy_weight": 1.0,  # C4: effective_cot=1.0 > 0.4
    }
    base.update(kwargs)
    return base


# --- Empty input ---

def test_empty_input_returns_empty():
    assert MF.run([]) == []


# --- Gate 1: mc_ev > 0 ---

def test_negative_mc_ev_rejected():
    assert MF.run([_c(mc_ev=-1)]) == []

def test_zero_mc_ev_rejected():
    assert MF.run([_c(mc_ev=0)]) == []

def test_positive_mc_ev_passes():
    # mc_ev=6 > 0 (C1) and >= min_ev=5.0 for proxy_w=1.0 (C5)
    assert len(MF.run([_c(mc_ev=6)])) == 1


# --- Gate 2: bs_edge > -0.10 ---

def test_bs_edge_too_negative_rejected():
    assert MF.run([_c(bs_edge=-0.11)]) == []

def test_bs_edge_exactly_minus_ten_passes():
    # Gate is strict < -0.10, so -0.10 itself passes
    assert len(MF.run([_c(bs_edge=-0.10)])) == 1

def test_bs_edge_just_above_threshold_passes():
    assert len(MF.run([_c(bs_edge=-0.09)])) == 1

def test_bs_edge_zero_passes():
    assert len(MF.run([_c(bs_edge=0.0)])) == 1


# --- Gate 3: iv_premium < 1.5 (IV not overheated) ---

def test_iv_overheat_rejected():
    assert MF.run([_c(iv_premium=1.6)]) == []

def test_iv_premium_at_threshold_passes():
    # Gate is strict >1.5, so exactly 1.5 passes
    assert len(MF.run([_c(iv_premium=1.5)])) == 1

def test_iv_premium_below_threshold_passes():
    assert len(MF.run([_c(iv_premium=1.49)])) == 1

def test_iv_premium_zero_passes():
    assert len(MF.run([_c(iv_premium=0.0)])) == 1


# --- Gate 4: edge_score >= 18 ---

def test_low_edge_score_rejected():
    assert MF.run([_c(edge_score=17)]) == []

def test_edge_score_exactly_18_passes():
    assert len(MF.run([_c(edge_score=18)])) == 1


# --- All gates pass ---

def test_good_candidate_passes_all_gates():
    result = MF.run([_c(mc_ev=30, bs_edge=0.02, edge_score=25)])
    assert len(result) == 1

def test_output_capped_at_20():
    candidates = [_c(mc_ev=10 + i) for i in range(30)]
    result = MF.run(candidates)
    assert len(result) <= 20


# --- Sort order ---

def test_sorted_by_mc_ev_descending():
    candidates = [_c(mc_ev=10), _c(mc_ev=50), _c(mc_ev=30)]
    result = MF.run(candidates)
    evs = [c["mc_ev"] for c in result]
    assert evs == sorted(evs, reverse=True)


# --- C4: Fundamentalkatalysator ---

def test_no_fundamental_rejected():
    # cot_z=0 × weight=1.0 = 0 < 0.4, mc_ev=10 < 20 → no fundamental
    assert MF.run([_c(cot_z=0.0, cot_proxy_weight=1.0, mc_ev=10)]) == []

def test_strong_cot_provides_fundamental():
    # effective_cot = 0.5 × 1.0 = 0.5 > 0.4 → fundamental satisfied
    assert len(MF.run([_c(cot_z=0.5, cot_proxy_weight=1.0, mc_ev=10)])) == 1

def test_high_mc_ev_provides_fundamental_without_cot():
    # mc_ev=20 >= 20 → fundamental satisfied even with no COT signal
    assert len(MF.run([_c(cot_z=0.0, cot_proxy_weight=1.0, mc_ev=20)])) == 1

def test_weak_proxy_nullifies_cot_fundamental():
    # effective_cot = 0.5 × 0.35 = 0.175 < 0.4, mc_ev=10 < 20 → rejected
    assert MF.run([_c(cot_z=0.5, cot_proxy_weight=0.35, mc_ev=10)]) == []


# --- C5: ETF-Abbildung / Proxy-EV-Kompensation ---

def test_perfect_proxy_low_ev_passes_c5():
    # proxy_w=1.0 → min_ev=5.0 → mc_ev=6 passes
    assert len(MF.run([_c(cot_proxy_weight=1.0, mc_ev=6, cot_z=1.0)])) == 1

def test_weak_proxy_needs_higher_ev():
    # proxy_w=0.35 → min_ev = 5 + 0.65×20 = 18.0
    # mc_ev=17 < 18 → rejected
    assert MF.run([_c(cot_proxy_weight=0.35, mc_ev=17, cot_z=0.0)]) == []

def test_weak_proxy_passes_with_sufficient_ev():
    # proxy_w=0.35 → min_ev=18.0; mc_ev=20 >= 18 AND mc_ev=20 >= 20 (C4)
    assert len(MF.run([_c(cot_proxy_weight=0.35, mc_ev=20, cot_z=0.0)])) == 1

def test_zero_proxy_requires_max_ev():
    # proxy_w=0.0 → min_ev = 5 + 1.0×20 = 25.0
    assert MF.run([_c(cot_proxy_weight=0.0, mc_ev=24, cot_z=0.0)]) == []
    assert len(MF.run([_c(cot_proxy_weight=0.0, mc_ev=25, cot_z=0.0)])) == 1
