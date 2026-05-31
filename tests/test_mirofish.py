"""Tests for MirofishChecker three-gate filter."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from analysis.mirofish_check import MirofishChecker

CFG = {"thresholds": {"mirofish_score_min": 18}}
MF  = MirofishChecker(CFG)


def _c(**kwargs):
    """Candidate that passes all gates by default."""
    base = {"mc_ev": 25.0, "bs_edge": 0.01, "edge_score": 20}
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
    assert len(MF.run([_c(mc_ev=0.01)])) == 1


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


# --- Gate 3: edge_score >= 18 ---

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
