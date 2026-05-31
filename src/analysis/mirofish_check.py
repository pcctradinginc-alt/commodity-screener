"""
MirofishChecker v4 — vier aufeinanderfolgende Gates:
  1. mc_ev > 0        (netto EV nach Ask-Fill + Kommission positiv)
  2. bs_edge > -0.10  (Option nicht >10% teurer als BS-Modell → kein IV-Datenfehler)
  3. iv_premium < 1.5 (market_iv < 2.5× HV → IV nicht überhitzt / Panik-Prämie)
  4. edge_score >= 18 (kombinierter Gesamtscore)

Gate 3 Begründung: Long-Optionen nach sichtbarer Panik verlieren selbst wenn
die Richtung stimmt, weil die IV-Prämie den Move mehr als aufzehrt.
iv_premium = market_iv/HV - 1.0; Schwelle 1.5 = market_iv ist 2.5× HV.
"""

IV_OVERHEAT_THRESHOLD = 1.5   # market_iv / hv > 2.5x → zu teuer für Long


class MirofishChecker:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.min_score = self.cfg.get("thresholds", {}).get("mirofish_score_min", 18)
        thr = self.cfg.get("thresholds", {})
        self.iv_overheat = float(thr.get("iv_overheat_threshold", IV_OVERHEAT_THRESHOLD))

    def run(self, candidates):
        if not candidates:
            print("  Mirofish passed: 0 candidates")
            return []

        passed = []
        rejected = {"mc_ev": 0, "bs_edge": 0, "iv_overheat": 0, "edge_score": 0}

        for c in candidates:
            if c.get("mc_ev", -999) <= 0:
                rejected["mc_ev"] += 1
                continue
            if c.get("bs_edge", -999) < -0.10:
                rejected["bs_edge"] += 1
                continue
            if c.get("iv_premium", 0) > self.iv_overheat:
                rejected["iv_overheat"] += 1
                continue
            if c.get("edge_score", 0) < self.min_score:
                rejected["edge_score"] += 1
                continue
            passed.append(c)

        print(
            f"  Mirofish: {len(passed)}/{len(candidates)} passed "
            f"(rejected: mc_ev≤0={rejected['mc_ev']}, "
            f"bs_edge<-10%={rejected['bs_edge']}, "
            f"iv_overheat={rejected['iv_overheat']}, "
            f"edge<{self.min_score}={rejected['edge_score']})"
        )

        passed.sort(key=lambda c: c.get("mc_ev", 0), reverse=True)
        return passed[:20]
