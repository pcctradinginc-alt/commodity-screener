"""
Claude Opus Final Analysis
Full context: quantitative scores + news + COT + EIA + FRED + positions
"""

import os
import json
import datetime
import anthropic


class ClaudeDeepAnalysis:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY", ""))

    def analyze(self, finalists, context):
        raw = context.get("raw_data", {})
        seg_scores = context.get("segment_scores", {})
        positions = context.get("positions", {})
        health = context.get("health", {})

        seg = finalists[0].get("segment", "unknown") if finalists else "unknown"
        seg_data = seg_scores.get(seg, {})
        news_hl = " | ".join(seg_data.get("top_headlines", [])[:3]) or "keine aktuellen Schlagzeilen"

        cot = raw.get("cot", {}).get(seg, {})
        eia = raw.get("eia", {}).get(seg, {})
        fred = raw.get("fred", {})
        data_as_of = raw.get("as_of", {})

        open_pos_str = json.dumps(
            [{"symbol": p["symbol"], "expiry": p["expiry"], "type": p["type"]}
             for p in positions.get("open_positions", [])],
            indent=2
        ) or "keine"

        candidates_str = json.dumps([{
            "symbol": c["symbol"],
            "strike": c["strike"],
            "expiry": c["expiry"],
            "type": c["option_type"],
            "dte": c["dte"],
            "delta": c["delta"],
            "mid_price": c["mid_price"],
            "fair_value_bs": c["fair_value_bs"],
            "edge_score": c["edge_score"],
            "mirofish_score": c.get("mirofish_score", 0),
            "mirofish_confidence": c.get("mirofish_confidence", "none"),
            "mc_ev": c["mc_ev"],
            "mc_win_prob": c["mc_win_prob"],
            "hist_win_rate": c["hist_win_rate"],
            "hist_sample_size": c["hist_sample_size"],
            "iv_pct": c["iv_pct"],
            "iv_rank": c["iv_rank"],
            "oi": c["oi"],
            "prophet_direction": c.get("prophet_direction", "neutral"),
            "prophet_confidence": c.get("prophet_confidence", 0),
        } for c in finalists[:8]], indent=2)

        today = datetime.date.today().isoformat()

        prompt = f"""Du bist ein erfahrener Commodity-Options-Analyst. Heute ist {today}.

SEGMENT: {seg.upper()} | Data as-of: {data_as_of.get(f'eia_{seg}', 'N/A')}

AKTUELLE SCHLAGZEILEN (letzte 24h):
{news_hl}

FUNDAMENTALDATEN:
- EIA Lagerdelta: {eia.get('delta', 'N/A')} | as-of: {eia.get('as_of', 'N/A')}
- CFTC COT Net-Commercial: {cot.get('net_commercial', 'N/A')} | as-of: {cot.get('as_of', 'N/A')}
- Fed Funds Rate: {fred.get('fed_funds_rate', 'N/A')}% | Real Yield 10Y: {fred.get('real_yield_10y', 'N/A')}%
- DXY: {fred.get('dxy', 'N/A')}

OFFENE POSITIONEN (keine Doppel-Entries):
{open_pos_str}

KANDIDATEN (nach Mirofish-Gate, max. 8):
{candidates_str}

DATA-HEALTH-SCORE: {health.get('score', 'N/A')}
HIGH_VOLATILITY_FLAG: {health.get('high_volatility_flag', False)}

AUFGABE:
1. Synthese: Stützen quantitative Scores, COT, EIA und News dieselbe Richtung? (2 Sätze konkret)
2. Wähle die beste Option aus den Kandidaten
3. Conviction-Score 1-10:
   Abzüge: -2 wenn News/Fundamentals widersprechen, -1 wenn IV-Rank < 35,
   -1 wenn Mirofish-Confidence = low oder none, -1 wenn HIGH_VOLATILITY_FLAG
4. Fair Value vs. Marktpreis (aus Kandidaten-Daten)
5. Max. Verlust
6. Expected Value aus Monte Carlo
7. Historische Win-Rate (Hinweis: spread-adjusted + as-of korrigiert)
8. Invalidierungs-Szenario (1 Satz)
9. News-Kontext (1 Satz)

ANTWORTE EXAKT in diesem Format (keine Abweichungen):
EMPFEHLUNG: [Symbol] [Strike] [Expiry] [Call/Put]
EINSTIEG: [Mid-Preis] (Limit zum Ask empfohlen)
FAIR VALUE: [BS-Preis] ([+/-X% vs. Markt])
CONVICTION: [1-10] — [Begründung 1 Satz]
MAX VERLUST: $[Prämie x 100]
EXPECTED VALUE: $[MC EV]
WIN-RATE HISTORISCH: [X%] (n=[Stichprobe], spread-adjusted, as-of korrigiert)
THESE: [1 Satz]
INVALIDIERUNG: [1 Satz]
NEWS: [1 Satz]
DATA AS-OF: {today} (Daten basieren auf US-Börsenschluss vom Vortag)"""

        try:
            response = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return self._parse_recommendation(text, finalists[0] if finalists else {})
        except Exception as e:
            print(f"  Claude Opus error: {e}")
            if finalists:
                c = finalists[0]
                return {
                    "symbol": c["symbol"],
                    "strike": c["strike"],
                    "expiry": c["expiry"],
                    "type": c["option_type"],
                    "mid_price": c["mid_price"],
                    "fair_value_bs": c["fair_value_bs"],
                    "edge_score": c["edge_score"],
                    "mirofish_score": c.get("mirofish_score", 0),
                    "mc_expected_value": c["mc_ev"],
                    "historical_win_rate": c["hist_win_rate"],
                    "conviction": 5,
                    "max_loss": round(c["mid_price"] * 100, 2),
                    "raw_text": f"Claude Opus error: {e}",
                    "segment": seg,
                }
            return {}

    def _parse_recommendation(self, text, top_candidate):
        """Parse Claude Opus structured output into dict."""
        lines = {line.split(":")[0].strip(): ":".join(line.split(":")[1:]).strip()
                 for line in text.split("\n") if ":" in line}

        def extract(key, default=""):
            for k, v in lines.items():
                if key.lower() in k.lower():
                    return v.strip()
            return default

        emp = extract("EMPFEHLUNG", "").split()
        symbol = emp[0] if emp else top_candidate.get("symbol", "")
        strike = float(emp[1]) if len(emp) > 1 else top_candidate.get("strike", 0)
        expiry = emp[2] if len(emp) > 2 else top_candidate.get("expiry", "")
        opt_type = emp[3] if len(emp) > 3 else top_candidate.get("option_type", "call")

        try:
            mid = float(extract("EINSTIEG", "0").split()[0].replace("$", ""))
        except (ValueError, IndexError):
            mid = top_candidate.get("mid_price", 0)

        try:
            conv_str = extract("CONVICTION", "5").split("—")[0].split("-")[0].strip()
            conviction = int(conv_str)
        except (ValueError, IndexError):
            conviction = 5

        try:
            ev_str = extract("EXPECTED VALUE", "0").replace("$", "").replace(",", "").split()[0]
            mc_ev = float(ev_str)
        except (ValueError, IndexError):
            mc_ev = top_candidate.get("mc_ev", 0)

        try:
            wr_str = extract("WIN-RATE", "50").replace("%", "").split()[0]
            win_rate = float(wr_str) / 100
        except (ValueError, IndexError):
            win_rate = top_candidate.get("hist_win_rate", 0.5)

        return {
            "symbol": symbol,
            "strike": strike,
            "expiry": expiry,
            "type": opt_type,
            "mid_price": mid,
            "fair_value_bs": top_candidate.get("fair_value_bs", 0),
            "edge_score": top_candidate.get("edge_score", 0),
            "mirofish_score": top_candidate.get("mirofish_score", 0),
            "mirofish_confidence": top_candidate.get("mirofish_confidence", "none"),
            "mc_expected_value": mc_ev,
            "historical_win_rate": win_rate,
            "historical_win_rate_spread_adjusted": True,
            "historical_win_rate_as_of_corrected": True,
            "sample_size": top_candidate.get("hist_sample_size", 0),
            "conviction": conviction,
            "max_loss": round(mid * 100, 2),
            "these": extract("THESE", ""),
            "invalidierung": extract("INVALIDIERUNG", ""),
            "news_context": extract("NEWS", ""),
            "synthesis": extract("Synthese", extract("SYNTHESE", "")),
            "raw_text": text,
            "segment": top_candidate.get("segment", ""),
            "oi": top_candidate.get("oi", 0),
        }
