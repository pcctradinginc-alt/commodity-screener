"""
Claude Haiku Preselection — reduziert Kandidaten auf Top-20
JETZT MIT STARKEM SPOT-PREIS- + MAKRO-KONTEXT (Phase 1)
"""

import os
import json
import datetime
import anthropic


class HaikuPreselect:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY", ""))

    def select(self, candidates):
        if not candidates:
            return []

        table = []
        for i, c in enumerate(candidates):
            table.append({
                "rank": i,
                "symbol": c["symbol"],
                "segment": c["segment"],
                "strike": c["strike"],
                "expiry": c["expiry"],
                "type": c["option_type"],
                "dte": c["dte"],
                "delta": c["delta"],
                "mid": c["mid_price"],
                "spot_price": c.get("spot_price", "N/A"),           # ← zentral
                "iv_pct": c["iv_pct"],
                "iv_rank": c["iv_rank"],
                "oi": c["oi"],
                "volume": c["volume"],
                "edge_score": c["edge_score"],
                "mc_ev": c["mc_ev"],
                "mc_win_prob": c["mc_win_prob"],
                "hist_win_rate": c["hist_win_rate"],
                "prophet_direction": c.get("prophet_direction", "neutral"),
            })

        prompt = f"""Du bist ein erfahrener Commodity-Options-Analyst. Heute ist {datetime.date.today().isoformat()}.

Aktueller Spot-Preis des Underlyings: {table[0].get('spot_price', 'N/A')} USD (sehr wichtig!).

Analysiere die folgenden {len(table)} Optionen und wähle die besten 20 aus.

**WICHTIG**: Bewerte das Sentiment und die Attraktivität immer im Kontext des aktuellen Spot-Preises!
Ein Put bei 105 $ ist nur sinnvoll, wenn der Spot wirklich stark fallen sollte — nicht nur weil alte Nachrichten "Öl bei 60 $" schreiben.

Priority criteria (in dieser Reihenfolge):
1. Liquidity (OI > 1000 und Volume > 50 bevorzugt)
2. Edge Score > 50
3. MC Expected Value positiv
4. IV-Rank > 40
5. Delta 0.25–0.40

Zusätzlich: Gib eine kurze, preisbezogene Begründung (z. B. "bullish, da Spot 116 $ und News von fallenden Rig Counts").

Candidates JSON:
{json.dumps(table, indent=2)}

Antworte **NUR** mit validem JSON:
{{
  "top20": [
    {{"rank": <original_rank>, "symbol": "...", "haiku_rank": 1, "haiku_reason": "kurzer Satz mit Spot-Preis-Bezug"}}
  ],
  "eliminated_count": <number>,
  "elimination_summary": "kurze Zusammenfassung"
}}"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                system="You are a quantitative options analyst. Respond only in valid JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            selected_ranks = {item["rank"] for item in result.get("top20", [])}
            top20 = [c for i, c in enumerate(candidates) if i in selected_ranks]

            print(f"  Haiku eliminated {result.get('eliminated_count', 0)}: "
                  f"{result.get('elimination_summary', '')}")
            return top20[:20]

        except Exception as e:
            print(f"  Haiku error: {e} — using edge score fallback")
            return sorted(candidates, key=lambda x: x.get("edge_score", 0), reverse=True)[:20]
