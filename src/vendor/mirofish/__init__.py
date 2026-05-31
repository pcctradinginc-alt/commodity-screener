"""
Mirofish Vendor Stub
-------------------
Place the real MiroFish-Offline files in this directory.

Source: https://github.com/nikmcfly/MiroFish-Offline
Pin the commit hash after vendorizing.

If not available, the MirofishChecker falls back to edge-score-based scoring.
The stub below provides the expected interface so imports don't fail.
"""


def simulate(candidate, raw_data=None):
    """
    Stub simulation — returns neutral score.
    Replace with real Mirofish implementation.

    Expected return format:
    {
        "score": 0-100,
        "confidence": "low" | "medium" | "high",
        "consensus": "bullish" | "bearish" | "neutral"
    }
    """
    edge = candidate.get("edge_score", 50)
    mc_ev = candidate.get("mc_ev", 0)
    hist_wr = candidate.get("hist_win_rate", 0.5)

    score = (
        edge * 0.4 +
        min(max(mc_ev / 500 * 30, 0), 30) +
        hist_wr * 30
    )
    score = min(100, max(0, score))

    if score >= 70:
        confidence = "medium"
    elif score >= 50:
        confidence = "low"
    else:
        confidence = "none"

    return {
        "score": round(score),
        "confidence": confidence,
        "consensus": "bullish" if score > 60 else "neutral",
        "stub": True,
    }
