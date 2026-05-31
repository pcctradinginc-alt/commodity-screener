"""
MirofishChecker v5 — sechs aufeinanderfolgende Gates:

  C1. mc_ev > 0         netto EV nach Ask-Fill + Kommission positiv
  C2. bs_edge > -0.10   Option nicht >10% teurer als BS-Modell
  C3. iv_premium < 1.5  market_iv < 2.5× HV (kein Panik-IV-Trade)
  C4. Fundamentalkatalysator: COT positioniert ODER MC-EV stark (≥20 USD)
  C5. ETF-Abbildung: schwacher Proxy erfordert höheren MC-EV als Kompensation
  C6. edge_score >= 18  kombinierter Gesamtscore

Zusammen implementieren sie: nur handeln wenn Momentum + Fundamentalkatalysator
+ akzeptable IV + gute ETF-Abbildung + Liquidität gleichzeitig positiv sind.
(Liquidität bereits im Kandidaten-Loop gefiltert: OI ≥ 80, Spread ≤ 30%.)
"""

IV_OVERHEAT_THRESHOLD = 1.5   # market_iv / hv > 2.5× → kein Long


class MirofishChecker:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        thr = self.cfg.get("thresholds", {})
        self.min_score   = float(thr.get("mirofish_score_min", 18))
        self.iv_overheat = float(thr.get("iv_overheat_threshold", IV_OVERHEAT_THRESHOLD))

    def run(self, candidates):
        if not candidates:
            print("  Mirofish passed: 0 candidates")
            return []

        passed = []
        rejected = {
            "mc_ev": 0, "bs_edge": 0, "iv_overheat": 0,
            "no_fundamental": 0, "weak_proxy_ev": 0, "edge_score": 0,
        }

        for c in candidates:
            # C1 — positive net EV
            if c.get("mc_ev", -999) <= 0:
                rejected["mc_ev"] += 1
                continue

            # C2 — IV data consistency
            if c.get("bs_edge", -999) < -0.10:
                rejected["bs_edge"] += 1
                continue

            # C3 — IV not overheated (no panic premium)
            if c.get("iv_premium", 0) > self.iv_overheat:
                rejected["iv_overheat"] += 1
                continue

            # C4 — at least one fundamental signal is positive:
            #   either COT is directionally positioned (z × proxy_weight > 0.4)
            #   or MC-EV is strong enough to stand alone (≥ $20 net)
            effective_cot = c.get("cot_z", 0) * c.get("cot_proxy_weight", 1.0)
            has_fundamental = effective_cot > 0.4 or c.get("mc_ev", 0) >= 20.0
            if not has_fundamental:
                rejected["no_fundamental"] += 1
                continue

            # C5 — weak ETF proxy requires stronger MC-EV to compensate
            #   proxy_w=1.0 → min_ev=$5 (normal gate)
            #   proxy_w=0.35 → min_ev=$18 (COPX/XLE need strong model signal)
            proxy_w = c.get("cot_proxy_weight", 1.0)
            min_ev = 5.0 + (1.0 - proxy_w) * 20.0
            if c.get("mc_ev", 0) < min_ev:
                rejected["weak_proxy_ev"] += 1
                continue

            # C6 — combined score
            if c.get("edge_score", 0) < self.min_score:
                rejected["edge_score"] += 1
                continue

            passed.append(c)

        print(
            f"  Mirofish: {len(passed)}/{len(candidates)} passed "
            f"(rej: mc_ev≤0={rejected['mc_ev']}, bs={rejected['bs_edge']}, "
            f"iv={rejected['iv_overheat']}, fundamental={rejected['no_fundamental']}, "
            f"proxy_ev={rejected['weak_proxy_ev']}, edge={rejected['edge_score']})"
        )

        passed.sort(key=lambda c: c.get("mc_ev", 0), reverse=True)
        return passed[:20]
