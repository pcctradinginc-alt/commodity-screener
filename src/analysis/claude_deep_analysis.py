"""
Claude Opus Final Analysis – Verbesserte Version
- Strenger Filter auf realistische Optionen (Delta 0.25-0.45)
- Explizite Ablehnung bei unrealistischen Moves (>12% in 30 Tagen)
- Automatische Conviction-Reduktion bei kleiner Historie
- Klarere No-Trade-Logik
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
        if not finalists:
            return self._no_trade_fallback()

        top = finalists[0]
        seg = top.get("segment", "unknown")
        spot = top.get("spot", "N/A")

        # Wichtige Kontext-Daten
        seg_data = context.get(seg, {})
        news_hl = " | ".join(seg_data.get("top_headlines", [])[:4]) or "Keine aktuellen Schlagzeilen"
        cot = context.get("raw_data", {}).get("cot", {}).get(top.get("ticker"), {})
        eia = context.get("raw_data", {}).get("eia", {}).get(top.get("ticker"), {})

        # Historische Warnung
        n = top.get("hist_sample_size", 0)
        hist_warning = f"\n⚠️ Historische Win-Rate basiert auf nur {n} Datenpunkten. Conviction wird automatisch reduziert!" if n < 20 else ""

        # Kandidaten als JSON für Claude
        candidates_str = json.dumps([{
            "symbol": c["symbol"],
            "strike": c["strike"],
            "expiry": c["expiry"],
            "type": c["option_type"],
            "dte": c["dte"],
            "delta": c.get("delta", 0.40),
            "mid_price": c.get("mid_price", 0),
            "edge_score": c.get("edge_score", 0),
            "mirofish_score": c.get("mirofish_score", 0),
            "hist_win_rate": c.get("hist_win_rate", 0.48),
            "hist_sample_size": c.get("hist_sample_size", 0),
        } for c in finalists[:6]], indent=2)

        today = datetime.date.today().isoformat()

        prompt = f"""Du bist ein sehr konservativer Commodity-Options-Trader. Heute ist {today}.
AKTUELLER SPOT-PREIS: {spot} USD ← SEHR WICHTIG!

{hist_warning}

REGELN (strikt einhalten):
- Empfehle NUR Optionen mit Delta zwischen 0.25 und 0.45 (realistische Wahrscheinlichkeit).
- Keine Deep-OTM-Optionen (kein Strike mehr als 12% vom Spot bei DTE < 60 Tagen).
- Bei unrealistischem Move (>12% in 30 Tagen) → sofort "KEIN TRADE EMPFOHLEN".
- Conviction max. 10/10. Bei n < 20 automatisch -2 Punkte.

SEGMENT: {seg.upper()}
NEWS (letzte Tage): {news_hl}
COT: Net Commercial = {cot.get('net_commercial', 'N/A')}
EIA: {eia.get('delta', 'N/A')}

KANDIDATEN:
{candidates_str}

**ANTWORTE STRENG EXAKT IM FOLGENDEN FORMAT. KEINE ABWEICHUNGEN, KEIN ZUSÄTZLICHER TEXT.**

EMPFEHLUNG: [Symbol] [Strike] [Expiry] [Call/Put]
EINSTIEG (MID): $[Mid-Preis]
FAIR VALUE BS: $[BS-Preis] oder n/a
CONVICTION: [1-10] — [kurze Begründung]
MAX. VERLUST: $[Praemie x 100]
MC EXP. VALUE: $[MC EV]
WIN-RATE HIST.: [X%] (n=[Stichprobe])
THESE: [1 Satz, was passieren muss]
INVALIDIERUNG: [1 Satz]
NEWS-KONTEXT: [1 Satz]

Falls kein Kandidat die Regeln erfüllt, schreibe exakt:
KEIN TRADE EMPFOHLEN
Mindest-Conviction fuer Trades: 6/10
"""

        try:
            response = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1200,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return self._parse_recommendation(text, top)

        except Exception as e:
            print(f" Claude Opus error: {e}")
            return self._no_trade_fallback()

    def _no_trade_fallback(self):
        return {
            "symbol": "NO TRADE",
            "strike": 0,
            "expiry": "",
            "type": "",
            "mid_price": 0,
            "fair_value_bs": 0,
            "conviction": 0,
            "max_loss": 0,
            "mc_expected_value": 0,
            "historical_win_rate": 0,
            "sample_size": 0,
            "these": "Keine ausreichend gute Setup gefunden",
            "invalidierung": "—",
            "news_context": "—",
            "raw_text": "NO TRADE FALLBACK",
        }

    def _parse_recommendation(self, text, top_candidate):
        # ... (die bestehende Parsing-Logik bleibt gleich – nur etwas robuster gemacht)
        lines = {line.split(":", 1)[0].strip().upper(): line.split(":", 1)[1].strip()
                 for line in text.split("\n") if ":" in line}

        def extract(key, default=""):
            for k, v in lines.items():
                if key.upper() in k:
                    return v.strip()
            return default

        emp = extract("EMPFEHLUNG", "").split()
        symbol = emp[0] if emp else top_candidate.get("symbol", "NO TRADE")
        strike = float(emp[1]) if len(emp) > 1 else top_candidate.get("strike", 0)
        expiry = emp[2] if len(emp) > 2 else top_candidate.get("expiry", "")
        opt_type = emp[3] if len(emp) > 3 else top_candidate.get("option_type", "call")

        try:
            conviction = int(extract("CONVICTION", "5").split("/")[0].split("-")[0].strip())
        except:
            conviction = 5

        # Automatische Reduktion bei kleiner Historie
        if top_candidate.get("hist_sample_size", 0) < 20:
            conviction = max(1, conviction - 2)

        return {
            "symbol": symbol,
            "strike": strike,
            "expiry": expiry,
            "type": opt_type,
            "mid_price": top_candidate.get("mid_price", 0),
            "fair_value_bs": top_candidate.get("fair_value_bs", 0),
            "conviction": conviction,
            "max_loss": round(top_candidate.get("mid_price", 0) * 100, 2),
            "mc_expected_value": top_candidate.get("mc_ev", 0),
            "historical_win_rate": top_candidate.get("hist_win_rate", 0.48),
            "sample_size": top_candidate.get("hist_sample_size", 0),
            "these": extract("THESE", "—"),
            "invalidierung": extract("INVALIDIERUNG", "—"),
            "news_context": extract("NEWS-KONTEXT", "—"),
            "raw_text": text,
            "segment": top_candidate.get("segment", ""),
        }
