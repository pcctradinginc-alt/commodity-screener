"""
MirofishChecker v3 — drei aufeinanderfolgende Gates:
  1. mc_ev > 0      (netto EV nach Ask-Fill + Kommission positiv)
  2. bs_edge > -0.10 (Option nicht >10% teurer als BS-Modell → kein IV-Datenfehler)
  3. edge_score >= 18 (kombinierter Gesamtscore)
"""


class MirofishChecker:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.min_score = self.cfg.get("thresholds", {}).get("mirofish_score_min", 18)

    def run(self, candidates):
        if not candidates:
            print("  Mirofish passed: 0 candidates")
            return []

        passed = []
        rejected = {"mc_ev": 0, "bs_edge": 0, "edge_score": 0}

        for c in candidates:
            if c.get("mc_ev", -999) <= 0:
                rejected["mc_ev"] += 1
                continue
            if c.get("bs_edge", -999) < -0.10:
                rejected["bs_edge"] += 1
                continue
            if c.get("edge_score", 0) < self.min_score:
                rejected["edge_score"] += 1
                continue
            passed.append(c)

        print(
            f"  Mirofish: {len(passed)}/{len(candidates)} passed "
            f"(rejected: mc_ev≤0={rejected['mc_ev']}, "
            f"bs_edge<-10%={rejected['bs_edge']}, "
            f"edge<{self.min_score}={rejected['edge_score']})"
        )

        passed.sort(key=lambda c: c.get("mc_ev", 0), reverse=True)
        return passed[:20]
