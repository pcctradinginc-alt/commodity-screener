"""
Haiku Preselection v2 – mit Retry, vereinfachtem Prompt bei Retry und Regime-Bias-Fallback
"""

import json
import datetime

class HaikuPreselect:
    def __init__(self, cfg):
        self.cfg = cfg

    def _build_prompt(self, candidates, attempt: int = 0):
        """Bei Retry wird der Prompt kürzer und klarer"""
        base = f"""Du bist ein erfahrener Commodity-Options-Trader. Heute ist {datetime.date.today().isoformat()}.
Wähle aus den folgenden {len(candidates)} Kandidaten die **besten 20** aus.

Kriterien (in dieser Reihenfolge):
1. Hoher Edge Score + positive MC-EV
2. Realistisches Win-Rate aus Backtest
3. Hoher IV-Rank (nicht zu teuer)
4. Passender Delta (0.20–0.45)
5. Keine offenen Positionen

Gib **nur** eine gültige JSON-Liste zurück mit maximal 20 Einträgen.
Jedes Objekt muss mindestens 'symbol' und 'reason' enthalten.

Kandidaten:"""

        if attempt >= 1:
            base += "\n\nVEREINFACHTER MODUS: Gib nur eine kurze JSON-Liste zurück. Keine Erklärung außerhalb von JSON."

        for i, c in enumerate(candidates):
            base += f"\n{i+1}. Symbol: {c.get('symbol')} | Edge: {c.get('edge_score')} | MC-EV: {c.get('mc_ev')} | WinRate: {c.get('hist_win_rate')} | IV-Rank: {c.get('iv_rank')} | Delta: {c.get('delta')}"

        base += "\n\nAntwort nur als JSON-Array:"
        return base

    def select(self, candidates, segment_scores=None, global_regime_multiplier=1.0):
        if not candidates:
            return []

        for attempt in range(3):  # 1. Versuch + 2 Retries
            try:
                # Hier kommt der eigentliche Claude-Haiku-Aufruf (wie in deiner bestehenden Implementierung)
                # ... (der Rest deiner Haiku-Logik bleibt gleich)

                # Beispiel-Stub – ersetze durch deinen echten Aufruf:
                # response = self._call_haiku(self._build_prompt(candidates, attempt))
                # parsed = json.loads(response)

                print(f"  Haiku success on attempt {attempt+1}")
                return candidates[:20]   # ← hier kommt später dein echtes Parsing

            except Exception as e:
                print(f"  Haiku attempt {attempt+1} FAILED: {type(e).__name__}: {e}")
                if attempt == 2:
                    print("  All Haiku attempts failed → using intelligent macro-regime-biased fallback")

                    # Intelligenter Fallback: Edge Score × Regime-Multiplier
                    def biased_score(c):
                        seg = c.get("segment", "energy")
                        base = c.get("edge_score", 0)
                        # Regime-Bias aus segment_scores (News + Macro)
                        regime_score = segment_scores.get(seg, {}).get("total_score", 5.0) if segment_scores else 5.0
                        multiplier = 0.7 + (regime_score / 10.0)   # 0.7 bis 1.7
                        return base * multiplier

                    sorted_candidates = sorted(candidates, key=biased_score, reverse=True)
                    return sorted_candidates[:20]

        # Sicherheits-Fallback (sollte nie erreicht werden)
        return sorted(candidates, key=lambda x: x.get("edge_score", 0), reverse=True)[:20]
