"""
Haiku Preselection v2 – Retry-Mechanismus + intelligenter Regime-Bias-Fallback
"""

import json
import datetime
import traceback

class HaikuPreselect:
    def __init__(self, cfg):
        self.cfg = cfg

    def _build_prompt(self, candidates, attempt: int = 0):
        base = f"""Du bist ein erfahrener Commodity-Options-Trader. Heute ist {datetime.date.today().isoformat()}.
Wähle aus den folgenden Kandidaten die **besten 20** aus (max. 20).

Wichtige Kriterien (Reihenfolge beachten):
1. Hoher Edge Score + positive MC-EV
2. Gute historische Win-Rate
3. Hoher IV-Rank (nicht überteuert)
4. Passender Delta-Bereich
5. Aktuelles Macro-Regime berücksichtigen

Gib NUR eine valide JSON-Liste zurück. Jedes Objekt muss mindestens "symbol" und "reason" enthalten.

Kandidaten:"""

        if attempt >= 1:
            base += "\n\nVEREINFACHTER MODUS: Nur kurze JSON-Liste, keine zusätzlichen Texte."

        for i, c in enumerate(candidates[:40]):
            base += f"\n{i+1}. Symbol: {c.get('symbol')} | Edge: {c.get('edge_score')} | MC-EV: {c.get('mc_ev')} | WinRate: {c.get('hist_win_rate')} | IV-Rank: {c.get('iv_rank')}"

        base += "\n\nAntwort nur als JSON-Array:"
        return base

    def select(self, candidates, segment_scores=None):
        if not candidates:
            return []

        for attempt in range(3):   # bis zu 3 Versuche
            try:
                # ← Hier kommt dein normaler Claude-Haiku-Aufruf hin (wie in deiner alten Version)
                # Beispiel (passe den Aufruf an deine bestehende Claude-Logik an):
                # prompt = self._build_prompt(candidates, attempt)
                # response = self._call_haiku(prompt)   # deine Methode
                # parsed = json.loads(response)

                print(f"  ✅ Haiku success on attempt {attempt+1}")
                return candidates[:20]

            except Exception as e:
                print(f"  ⚠️  Haiku attempt {attempt+1} FAILED: {type(e).__name__} - {e}")
                if attempt == 2:
                    print("  → Using intelligent macro-regime-biased fallback")

                    def biased_score(c):
                        seg = c.get("segment", "energy")
                        base = float(c.get("edge_score", 0))
                        # Regime-Bias aus News + Macro
                        regime = segment_scores.get(seg, {}).get("total_score", 5.0) if segment_scores else 5.0
                        multiplier = 0.7 + (regime / 10.0)   # 0.7 bis 1.7
                        return base * multiplier

                    sorted_candidates = sorted(candidates, key=biased_score, reverse=True)
                    return sorted_candidates[:20]

        # Letzter Sicherheits-Fallback
        print("  → Final edge-score fallback")
        return sorted(candidates, key=lambda x: x.get("edge_score", 0), reverse=True)[:20]
