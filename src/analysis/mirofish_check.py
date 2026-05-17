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
            mc_ev    = c.get("mc_ev", 0)
            bs_edge  = c.get("bs_edge", 0)
            edge     = c.get("edge_score", 0)

            # Require positive EV from both MC and BS, plus minimum edge score
            if mc_ev > 0 and bs_edge > 0 and edge >= self.min_score:
                passed.append(c)

        # Sort by combined quality: MC-EV weight + BS-edge weight
        passed.sort(
            key=lambda c: 0.5 * c.get("mc_ev", 0) + 0.5 * c.get("bs_edge", 0) * 100,
            reverse=True,
        )

        print(f"  Mirofish passed: {len(passed)} / {len(candidates)} "
              f"(mc_ev>0 AND bs_edge>0 AND edge≥{self.min_score})")
        return passed[:20]
