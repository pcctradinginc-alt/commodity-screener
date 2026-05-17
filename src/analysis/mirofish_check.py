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
            mc_ev   = c.get("mc_ev", 0)
            bs_edge = c.get("bs_edge", 0)
            edge    = c.get("edge_score", 0)

            # Softer gate: MC-EV positive OR BS only slightly overvalued vs HV.
            # Strict AND was too aggressive: when market IV > HV (common in uncertain
            # markets), bs_edge is structurally negative → everything would be filtered.
            ev_ok   = mc_ev > 0 or bs_edge > -0.05
            if ev_ok and edge >= 18:
                passed.append(c)

        # Sort by combined quality: MC-EV weight + BS-edge weight
        passed.sort(
            key=lambda c: 0.5 * c.get("mc_ev", 0) + 0.5 * c.get("bs_edge", 0) * 100,
            reverse=True,
        )

        print(f"  Mirofish passed: {len(passed)} / {len(candidates)} "
              f"(mc_ev>0 OR bs_edge>-0.05) AND edge≥18")
        return passed[:20]
