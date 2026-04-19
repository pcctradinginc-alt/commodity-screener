"""
Claude Opus Final Analysis
FINAL VERSION mit:
- Automatische Conviction-Reduktion bei n=0
- Klarer Warnung bei unzureichender Historie
- Strengerem Prompt für bessere Format-Treue
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

        spot_price = finalists[0].get("spot_price", "N/A") if finalists else "N/A"

        # ── NEU: Warnung bei unzureichender Historie ─────────────────
        sample_size = finalists[0].get("hist_sample_size", 0)
        hist_warning = ""
        if sample_size < 20:
            hist_warning = f"\n⚠️  WICHTIG: Historische Win-Rate basiert auf nur {sample_size} Datenpunkten (Fallback 48%). Conviction wird automatisch um 2 Punkte reduziert!"

        news_warning = ""
        if any(ind in news_hl.lower() for ind in ["$60", "60 $", "brent breaks $60", "oil at 60"]):
            news_warning = "\n⚠️  WARNUNG: Einige Schlagzeilen enthalten veraltete Preise. Ignoriere alte News und priorisiere Spot-Preis + Fundamentaldaten!"

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
            "mc_ev": c["mc_ev"],
            "hist_win_rate": c["hist_win_rate"],
            "hist_sample_size": c["hist_sample_size"],
            "iv_pct": c["iv_pct"],
            "iv_rank": c["iv_rank"],
            "oi": c["oi"],
        } for c in finalists[:8]], indent=2)

        today = datetime.date.today().isoformat()

        prompt = f"""Du bist ein erfahrener Commodity-Options-Analyst. Heute ist {today}.
AKTUELLER SPOT-PREIS: {spot_price} USD ← SEHR WICHTIG!
{hist_warning}
{news_warning}

WICHTIG: Empfehle ausschließlich LONG-Optionen (Kauf Calls oder Puts).

SEGMENT: {seg.upper()}

AKTUELLE SCHLAGZEILEN (letzte 10 Tage):
{news_hl}

FUNDAMENTALDATEN:
- EIA Lagerdelta: {eia.get('delta', 'N/A')}
- COT Net-Commercial: {cot.get('net_commercial', 'N/A')}
- Fed Funds Rate: {fred.get('fed_funds_rate', 'N/A')}% | DXY: {fred.get('dxy', 'N/A')}

KANDIDATEN:
{candidates_str}

AUFGABE:
1. Synthese: Zeigen COT, EIA, News und Spot-Preis dieselbe Richtung?
2. Wähle die beste LONG-Option.
3. Conviction 1-10. Bei hist_sample_size < 20 → Conviction automatisch -2!
4. Fair Value, Max Verlust, MC EV, These, Invalidierung, News-Kontext.

**ANTWORTE STRENG EXAKT IM FOLGENDEN FORMAT. KEINE ABWEICHUNGEN.**
EMPFEHLUNG: [Symbol] [Strike] [Expiry] [Call/Put]
EINSTIEG: [Mid-Preis]
FAIR VALUE: [BS-Preis] ([+/-X% vs. Markt] oder n/a)
CONVICTION: [1-10] — [Begründung 1 Satz]
MAX VERLUST: $[Praemie x 100]
EXPECTED VALUE: $[MC EV]
WIN-RATE HISTORISCH: [X%] (n=[Stichprobe])
THESE: [1 Satz — was muss passieren]
INVALIDIERUNG: [1 Satz]
NEWS: [1 Satz]
DATA AS-OF: {today}"""

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
                    "sample_size": c.get("hist_sample_size", 0),
                    "conviction": 5,
                    "max_loss": round(c["mid_price"] * 100, 2),
                    "raw_text": f"Claude Opus error: {e}",
                    "segment": seg,
                }
            return {}

    def _parse_recommendation(self, text, top_candidate):
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
        except:
            mid = top_candidate.get("mid_price", 0)

        try:
            conv_str = extract("CONVICTION", "5").split("—")[0].split("-")[0].strip()
            conviction = int(conv_str)
        except:
            conviction = 5

        # NEU: Automatischer Conviction-Abzug bei n=0
        sample_size = top_candidate.get("hist_sample_size", 0)
        if sample_size < 20:
            conviction = max(1, conviction - 2)

        try:
            ev_str = extract("EXPECTED VALUE", "0").replace("$", "").replace(",", "").split()[0]
            mc_ev = float(ev_str)
        except:
            mc_ev = top_candidate.get("mc_ev", 0)

        try:
            wr_str = extract("WIN-RATE", "50").replace("%", "").split()[0]
            win_rate = float(wr_str) / 100
        except:
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
            "mc_expected_value": mc_ev,
            "historical_win_rate": win_rate,
            "sample_size": sample_size,
            "conviction": conviction,
            "max_loss": round(mid * 100, 2),
            "these": extract("THESE", "—"),
            "invalidierung": extract("INVALIDIERUNG", "—"),
            "news_context": extract("NEWS", "—"),
            "raw_text": text,
            "segment": top_candidate.get("segment", ""),
            "oi": top_candidate.get("oi", 0),
        }
