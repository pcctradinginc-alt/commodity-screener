"""
Claude Deep Analysis v2 — EIA/FRED/COT korrekt übergeben, Felder aktualisiert
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
        seg  = top.get("segment", "unknown")
        spot = top.get("spot", "N/A")

        seg_data  = context.get(seg, {})
        news_hl   = " | ".join(seg_data.get("top_headlines", [])[:4]) or "Keine aktuellen Schlagzeilen"

        # raw_data is injected by main.py into context["raw_data"]
        raw_data  = context.get("raw_data", {})
        ticker    = top.get("ticker", "")

        cot  = raw_data.get("cot", {}).get(ticker, {})
        eia  = raw_data.get("eia", {}).get(seg, {})
        fred = raw_data.get("fred", {})

        # COT summary
        cot_summary = (
            f"Signal={cot.get('signal_strength','N/A')} | "
            f"Net={cot.get('net_commercial','N/A'):,} | "
            f"Z-Score={cot.get('z_score','N/A'):.2f} | "
            f"OI-Ratio={cot.get('commercial_oi_ratio','N/A'):.1f}%"
        ) if cot.get("signal_strength") else "N/A"

        # EIA summary
        eia_lines = []
        for sid, sdata in eia.items():
            eia_lines.append(
                f"{sid}: {sdata.get('latest','?')} (Δ{sdata.get('delta',0):+.1f} / {sdata.get('pct_change',0):+.1f}%)"
            )
        eia_summary = " | ".join(eia_lines) if eia_lines else "N/A"

        # FRED summary
        fred_parts = []
        if fred.get("dollar_index"):
            fred_parts.append(f"DXY={fred['dollar_index']:.1f}")
        if fred.get("treasury_10y"):
            fred_parts.append(f"10y={fred['treasury_10y']:.2f}%")
        if fred.get("fed_funds_rate"):
            fred_parts.append(f"FedFunds={fred['fed_funds_rate']:.2f}%")
        fred_summary = " | ".join(fred_parts) if fred_parts else "N/A"

        n = top.get("hist_sample_size", 0)
        hist_warning = (
            f"\n⚠️ Historische Win-Rate basiert auf nur {n} Datenpunkten — Conviction wird reduziert!"
            if n < 20 else ""
        )

        candidates_str = json.dumps([{
            "symbol":           c["symbol"],
            "strike":           c["strike"],
            "expiry":           c["expiry"],
            "type":             c["option_type"],
            "dte":              c["dte"],
            "delta":            round(c.get("delta", 0.35), 3),
            "mid_price":        c.get("mid_price", 0),
            "fair_value_bs":    c.get("fair_value_bs", 0),
            "bs_edge":          c.get("bs_edge", 0),
            "mc_ev":            c.get("mc_ev", 0),
            "mc_win_prob":      c.get("mc_win_prob", 0),
            "edge_score":       round(c.get("edge_score", 0), 1),
            "hist_win_rate":    c.get("hist_win_rate", 0.48),
            "hist_sample_size": c.get("hist_sample_size", 0),
            "cot_strength":     c.get("cot_strength", 1.0),
            "macro_multiplier":     c.get("macro_multiplier", 1.0),
            "prophet_direction":    c.get("prophet_direction", "neutral"),
            "aschenbrenner_bias":   c.get("aschenbrenner_bias", 0),
            "call_skew_ratio":      c.get("call_skew_ratio", 1.0),
        } for c in finalists[:6]], indent=2)

        today = datetime.date.today().isoformat()

        prompt = f"""Du bist ein sehr konservativer Commodity-Options-Trader. Heute ist {today}.
AKTUELLER SPOT-PREIS: {spot} USD ← SEHR WICHTIG!

{hist_warning}

REGELN (strikt einhalten):
- Nur Optionen mit Delta 0.20–0.45 empfehlen.
- Keine Deep-OTM-Optionen (Strike >12% vom Spot bei DTE < 60 Tagen).
- Nur Optionen mit bs_edge > 0 (günstig vs. HV-Fair-Value) und mc_ev > 0 empfehlen.
- Bei unrealistischem Move oder negativem EV → "KEIN TRADE EMPFOHLEN".

SEGMENT: {seg.upper()}
NEWS: {news_hl}

FUNDAMENTALDATEN:
COT: {cot_summary}
EIA: {eia_summary}
FRED/MAKRO: {fred_summary}
MACRO-MULTIPLIER: {top.get('macro_multiplier', 1.0):.2f} (>1 = Tailwind, <1 = Headwind)
AI-INFRA BIAS: +{top.get('aschenbrenner_bias', 0):.1f} Punkte | Call-Skew: {top.get('call_skew_ratio', 1.0):.3f}

KANDIDATEN (sortiert nach Edge-Score):
{candidates_str}

Erläuterung der Felder:
- bs_edge: (BS-Fair-Value(HV) - Mid) / Mid — positiv = Option günstig
- mc_ev: Monte-Carlo Expected Value in USD pro Kontrakt
- edge_score: kombinierter Score (COT 35% + BS 35% + MC 20% + Hist 10%) × Macro-Multiplier
- macro_multiplier: EIA-Inventory-Signal × FRED-Dollar/Zins-Regime

**ANTWORTE STRENG EXAKT IM FOLGENDEN FORMAT. KEINE ABWEICHUNGEN.**

EMPFEHLUNG: [Symbol] [Strike] [Expiry] [Call/Put]
EINSTIEG (MID): $[Mid-Preis]
FAIR VALUE BS: $[BS-Preis] oder n/a
CONVICTION: [1-10] — [kurze Begründung]
MAX. VERLUST: $[Praemie x 100]
MC EXP. VALUE: $[MC EV]
WIN-RATE HIST.: [X%] (n=[Stichprobe])
THESE: [1 Satz]
INVALIDIERUNG: [1 Satz]
NEWS-KONTEXT: [1 Satz]

Falls kein Kandidat die Regeln erfüllt, schreibe exakt:
KEIN TRADE EMPFOHLEN
Mindest-Conviction fuer Trades: 6/10
"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return self._parse_recommendation(text, top)

        except Exception as e:
            print(f"  Claude error: {e}")
            return self._no_trade_fallback()

    def _no_trade_fallback(self):
        return {
            "symbol":               "NO TRADE",
            "strike":               0,
            "expiry":               "",
            "type":                 "",
            "mid_price":            0,
            "fair_value_bs":        0,
            "conviction":           0,
            "max_loss":             0,
            "mc_expected_value":    0,
            "historical_win_rate":  0,
            "sample_size":          0,
            "these":                "Kein ausreichend gutes Setup gefunden",
            "invalidierung":        "—",
            "news_context":         "—",
            "raw_text":             "NO TRADE FALLBACK",
        }

    def _parse_recommendation(self, text, top_candidate):
        if "KEIN TRADE" in text.upper() or "NO TRADE" in text.upper():
            return self._no_trade_fallback()

        lines = {
            line.split(":", 1)[0].strip().upper(): ":".join(line.split(":", 1)[1:]).strip()
            for line in text.split("\n") if ":" in line
        }

        def extract(key, default=""):
            for k, v in lines.items():
                if key.upper() in k:
                    return v.strip()
            return default

        raw_emp = extract("EMPFEHLUNG", "").split()
        symbol   = raw_emp[0] if raw_emp else top_candidate.get("symbol", "NO TRADE")
        strike   = float(raw_emp[1]) if len(raw_emp) > 1 else top_candidate.get("strike", 0)
        expiry   = raw_emp[2] if len(raw_emp) > 2 else top_candidate.get("expiry", "")
        opt_type = raw_emp[3] if len(raw_emp) > 3 else top_candidate.get("option_type", "call")

        try:
            conviction = int(extract("CONVICTION", "5").split("/")[0].split("—")[0].strip())
        except:
            conviction = 5

        # Auto-reduce conviction if sample size too small
        if top_candidate.get("hist_sample_size", 0) < 20:
            conviction = max(1, conviction - 2)

        return {
            "symbol":               symbol,
            "strike":               strike,
            "expiry":               expiry,
            "type":                 opt_type,
            "mid_price":            top_candidate.get("mid_price", 0),
            "fair_value_bs":        top_candidate.get("fair_value_bs", 0),
            "bs_edge":              top_candidate.get("bs_edge", 0),
            "conviction":           conviction,
            "max_loss":             round(top_candidate.get("mid_price", 0) * 100, 2),
            "mc_expected_value":    top_candidate.get("mc_ev", 0),
            "historical_win_rate":  top_candidate.get("hist_win_rate", 0.48),
            "sample_size":          top_candidate.get("hist_sample_size", 0),
            "edge_score":           top_candidate.get("edge_score", 0),
            "macro_multiplier":     top_candidate.get("macro_multiplier", 1.0),
            "these":                extract("THESE", "—"),
            "invalidierung":        extract("INVALIDIERUNG", "—"),
            "news_context":         extract("NEWS-KONTEXT", "—"),
            "raw_text":             text,
            "segment":              top_candidate.get("segment", ""),
            "ticker":               top_candidate.get("ticker", ""),
        }
