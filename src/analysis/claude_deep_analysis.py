"""
Claude Deep Analysis v3

Conviction score is computed deterministically from quantitative inputs.
Claude (temperature=0) generates text commentary only:
  THESE, INVALIDIERUNG, NEWS-KONTEXT

This makes the gate reproducible and auditable — Claude cannot override
a bad score or inflate a marginal setup.
"""

import os
import json
import datetime
import anthropic


def compute_conviction(candidate: dict) -> int:
    """
    Rule-based conviction 1–9 from quantitative signals.
    Maximum raw score = 10; mapped to int 1–9.

    Points:
      MC EV (net, post-cost):     0–3
      MC win probability:         0–2
      Historical win rate (n≥30): 0–2
      COT z-score:                0–2
      Edge score:                 0–1
    """
    score = 0.0

    # MC Expected Value (USD, net of ask + commission)
    mc_ev = candidate.get("mc_ev", 0)
    if mc_ev > 50:
        score += 3.0
    elif mc_ev > 20:
        score += 2.0
    elif mc_ev > 5:
        score += 1.0

    # MC win probability
    win_prob = candidate.get("mc_win_prob", 0)
    if win_prob > 0.55:
        score += 2.0
    elif win_prob > 0.50:
        score += 1.0

    # Historical win rate — only counts if sample is statistically meaningful
    hist_wr = candidate.get("hist_win_rate", 0.48)
    n = candidate.get("hist_sample_size", 0)
    if n >= 30:
        if hist_wr > 0.55:
            score += 2.0
        elif hist_wr > 0.50:
            score += 1.0

    # COT z-score (directional futures positioning)
    cot_z = candidate.get("cot_z", 0.0)
    if cot_z > 1.5:
        score += 2.0
    elif cot_z > 1.0:
        score += 1.0

    # Combined edge score
    if candidate.get("edge_score", 0) > 30:
        score += 1.0

    return min(9, max(1, round(score)))


class ClaudeDeepAnalysis:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY", ""))
        self.conviction_min = cfg.get("thresholds", {}).get("conviction_min_for_trade", 6)

    def analyze(self, finalists, context):
        if not finalists:
            return self._no_trade_fallback()

        top  = finalists[0]
        seg  = top.get("segment", "unknown")
        spot = top.get("spot", "N/A")

        # Compute conviction before calling Claude
        conviction = compute_conviction(top)
        if conviction < self.conviction_min:
            print(f"  Conviction {conviction} < {self.conviction_min} → no trade")
            return self._no_trade_fallback()

        seg_data = context.get(seg, {})
        news_hl  = " | ".join(seg_data.get("top_headlines", [])[:4]) or "Keine aktuellen Schlagzeilen"

        raw_data = context.get("raw_data", {})
        ticker   = top.get("ticker", "")

        cot  = raw_data.get("cot", {}).get(ticker, {})
        eia  = raw_data.get("eia", {}).get(seg, {})
        fred = raw_data.get("fred", {})

        cot_summary = (
            f"Signal={cot.get('signal_strength','N/A')} | "
            f"Net={cot.get('net_commercial','N/A'):,} | "
            f"Z-Score={cot.get('z_score','N/A'):.2f} | "
            f"OI-Ratio={cot.get('commercial_oi_ratio','N/A'):.1f}%"
        ) if cot.get("signal_strength") else "N/A"

        eia_lines = [
            f"{sid}: {sd.get('latest','?')} (Δ{sd.get('delta',0):+.1f} / {sd.get('pct_change',0):+.1f}%)"
            for sid, sd in eia.items()
        ]
        eia_summary = " | ".join(eia_lines) if eia_lines else "N/A"

        fred_parts = []
        if fred.get("dollar_index"):  fred_parts.append(f"DXY={fred['dollar_index']:.1f}")
        if fred.get("treasury_10y"):  fred_parts.append(f"10y={fred['treasury_10y']:.2f}%")
        if fred.get("fed_funds_rate"): fred_parts.append(f"FedFunds={fred['fed_funds_rate']:.2f}%")
        fred_summary = " | ".join(fred_parts) if fred_parts else "N/A"

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
            "macro_multiplier": c.get("macro_multiplier", 1.0),
            "prophet_direction": c.get("prophet_direction", "neutral"),
            "call_skew_ratio":  c.get("call_skew_ratio", 1.0),
        } for c in finalists[:6]], indent=2)

        today = datetime.date.today().isoformat()

        prompt = f"""Du bist ein konservativer Commodity-Options-Analyst. Heute ist {today}.

Der quantitative Screening-Prozess hat folgenden Kandidaten ausgewählt:
Conviction: {conviction}/9 (regelbasiert berechnet — nicht verändern)

SEGMENT: {seg.upper()} | SPOT: {spot} USD
NEWS: {news_hl}

FUNDAMENTALDATEN:
COT: {cot_summary}
EIA: {eia_summary}
FRED/MAKRO: {fred_summary}

KANDIDATEN (Top 6, sortiert nach MC-EV):
{candidates_str}

Deine Aufgabe: Liefere ausschließlich die drei Textfelder unten.
Keine Zahlen verändern. Keine eigene Conviction. Kein Trade-Urteil.
Schreibe präzise, faktenbasiert, je 1 Satz.

THESE: [Warum diese Option jetzt, basierend auf COT/EIA/Makro]
INVALIDIERUNG: [Welches Ereignis würde die These widerlegen]
NEWS-KONTEXT: [Relevanteste aktuelle Schlagzeile und ihre Bedeutung]
"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            print(f"  Claude text output logged ({len(text)} chars)")
        except Exception as e:
            print(f"  Claude error: {e}")
            text = "THESE: — | INVALIDIERUNG: — | NEWS-KONTEXT: —"

        return self._build_recommendation(top, conviction, text)

    def _build_recommendation(self, top, conviction, claude_text):
        lines = {
            line.split(":", 1)[0].strip().upper(): line.split(":", 1)[1].strip()
            for line in claude_text.split("\n") if ":" in line
        }

        def extract(key):
            for k, v in lines.items():
                if key.upper() in k:
                    return v.strip()
            return "—"

        return {
            "symbol":              top.get("symbol", "NO TRADE"),
            "strike":              top.get("strike", 0),
            "expiry":              top.get("expiry", ""),
            "type":                top.get("option_type", ""),
            "mid_price":           top.get("mid_price", 0),
            "fair_value_bs":       top.get("fair_value_bs", 0),
            "bs_edge":             top.get("bs_edge", 0),
            "conviction":          conviction,
            "max_loss":            round(top.get("mid_price", 0) * 100, 2),
            "mc_expected_value":   top.get("mc_ev", 0),
            "mc_win_prob":         top.get("mc_win_prob", 0),
            "historical_win_rate": top.get("hist_win_rate", 0.48),
            "sample_size":         top.get("hist_sample_size", 0),
            "edge_score":          top.get("edge_score", 0),
            "macro_multiplier":    top.get("macro_multiplier", 1.0),
            "cot_z":               top.get("cot_z", 0.0),
            "these":               extract("THESE"),
            "invalidierung":       extract("INVALIDIERUNG"),
            "news_context":        extract("NEWS-KONTEXT"),
            "raw_text":            claude_text,
            "segment":             top.get("segment", ""),
            "ticker":              top.get("ticker", ""),
        }

    def _no_trade_fallback(self):
        return {
            "symbol":              "NO TRADE",
            "strike":              0,
            "expiry":              "",
            "type":                "",
            "mid_price":           0,
            "fair_value_bs":       0,
            "conviction":          0,
            "max_loss":            0,
            "mc_expected_value":   0,
            "mc_win_prob":         0,
            "historical_win_rate": 0,
            "sample_size":         0,
            "these":               "Kein ausreichend gutes Setup gefunden",
            "invalidierung":       "—",
            "news_context":        "—",
            "raw_text":            "NO TRADE FALLBACK",
        }
