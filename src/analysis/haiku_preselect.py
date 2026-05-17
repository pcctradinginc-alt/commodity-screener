"""
Haiku Preselection v3 — echter Claude Haiku API-Call mit Retry + Fallback
"""

import json
import re
import os
import datetime
import anthropic


class HaikuPreselect:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY", ""))

    def _build_prompt(self, candidates, attempt: int = 0):
        today = datetime.date.today().isoformat()
        intro = f"""Du bist ein erfahrener Commodity-Options-Trader. Heute ist {today}.
Wähle aus den folgenden Kandidaten die **besten 20** aus (maximal 20).

Kriterien (absteigend nach Wichtigkeit):
1. Positiver BS-Edge (bs_edge > 0): Option günstig vs. HV-Fair-Value
2. Positive MC-EV (mc_ev > 0): Erwartungswert positiv
3. Hoher COT-Strength-Faktor (cot_strength > 1.0)
4. Gute historische Win-Rate (hist_win_rate)
5. Hoher IV-Rank und Edge Score

Antworte NUR mit einem validen JSON-Array. Kein Text davor oder danach.
Jedes Objekt muss "symbol" und "reason" (max. 10 Wörter) enthalten.

Kandidaten:"""

        if attempt >= 1:
            intro += "\n\n[VEREINFACHT: Nur JSON-Liste, keine Erklärungen außerhalb]"

        for i, c in enumerate(candidates[:40]):
            intro += (
                f"\n{i+1}. {c.get('symbol')} | bs_edge={c.get('bs_edge', 0):.3f}"
                f" | mc_ev={c.get('mc_ev', 0):.1f} | cot={c.get('cot_strength', 1):.1f}"
                f" | win_rate={c.get('hist_win_rate', 0.48):.2f} | dte={c.get('dte')}"
                f" | delta={c.get('delta', 0):.2f} | edge={c.get('edge_score', 0):.1f}"
            )

        intro += "\n\nJSON-Array:"
        return intro

    def select(self, candidates, segment_scores=None):
        if not candidates:
            return []

        for attempt in range(3):
            try:
                prompt = self._build_prompt(candidates, attempt)
                response = self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1500,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text.strip()

                # Extract JSON array (robust against surrounding text)
                json_match = re.search(r"\[.*\]", text, re.DOTALL)
                if not json_match:
                    raise ValueError("No JSON array in response")

                parsed = json.loads(json_match.group())
                symbols = {p["symbol"] for p in parsed if isinstance(p, dict) and "symbol" in p}
                selected = [c for c in candidates if c.get("symbol") in symbols]

                if selected:
                    print(f"  ✅ Haiku selected {len(selected)} candidates (attempt {attempt+1})")
                    return selected[:20]
                raise ValueError("No matching symbols found")

            except Exception as e:
                print(f"  ⚠️  Haiku attempt {attempt+1} failed: {type(e).__name__} — {e}")

        # Fallback: rank by combined score with segment-news bias
        print("  → Fallback: edge_score + news-bias ranking")

        def biased_score(c):
            seg = c.get("segment", "")
            base = float(c.get("edge_score", 0))
            regime = segment_scores.get(seg, {}).get("total_score", 5.0) if segment_scores else 5.0
            return base * (0.7 + regime / 10.0)

        return sorted(candidates, key=biased_score, reverse=True)[:20]
