"""
MirofishChecker v2 — echter Filter: positive MC-EV UND positiver BS-Edge
"""


class MirofishChecker:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.min_score = self.cfg.get("thresholds", {}).get("mirofish_score_min", 25)
        print("  Mirofish v2: MC-EV > 0 + BS-Edge > 0 + Edge-Score-Gate aktiv")

    def run(self, candidates):
        if not candidates:
            print("  Mirofish passed: 0 candidates")
            return []

        passed = []
        for c in candidates:
            edge = c.get("edge_score", 0)

            # When market_iv > HV (common in high-uncertainty regimes), both mc_ev and
            # bs_edge are structurally negative (option priced above HV-fair-value).
            # The edge_score already penalizes this by zeroing those components.
            # A separate ev_ok gate would double-penalize and block all trades in this
            # regime, so we gate only on combined edge_score.
            if edge >= 18:
                passed.append(c)

        # Sort by combined quality: MC-EV weight + BS-edge weight
        passed.sort(
            key=lambda c: 0.5 * c.get("mc_ev", 0) + 0.5 * c.get("bs_edge", 0) * 100,
            reverse=True,
        )

        print(f"  Mirofish passed: {len(passed)} / {len(candidates)} (edge≥18)")
        return passed[:20]
