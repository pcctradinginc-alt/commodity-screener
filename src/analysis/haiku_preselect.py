"""
Claude Haiku Preselection — reduces candidates to Top-20
"""

import os
import json
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

        prompt = f"""You are a quantitative options analyst. Analyze these {len(table)} option candidates
and select the best 20 (or fewer if less than 20 exist).

Priority criteria (in order):
1. Liquidity: OI > 1000 and volume > 50 preferred
2. Edge score > 50 (theoretical undervaluation)
3. MC expected value positive
4. IV rank > 40 (elevated premium environment)
5. Delta 0.25-0.40 (directional but not deep ITM)

Candidates JSON:
{json.dumps(table, indent=2)}

Respond ONLY with valid JSON, no other text:
{{
  "top20": [
    {{"rank": <original_rank>, "symbol": "...", "haiku_rank": 1, "haiku_reason": "one sentence"}}
  ],
  "eliminated_count": <number>,
  "elimination_summary": "brief reason"
}}"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
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
            return sorted(candidates, key=lambda x: x["edge_score"], reverse=True)[:20]
