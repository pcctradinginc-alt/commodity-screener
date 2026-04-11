"""
HTML Trading Card Generator
Mobile-friendly, inline CSS, conviction color coding
"""

import datetime


class HTMLCardGenerator:
    def __init__(self, cfg):
        self.cfg = cfg

    def _conviction_color(self, score):
        if score >= 8: return "#16a34a"
        if score >= 5: return "#ca8a04"
        return "#dc2626"

    def generate(self, rec, seg_scores, health, positions):
        if not rec:
            return self._error_card("No recommendation generated")

        seg = rec.get("segment", "")
        seg_data = seg_scores.get(seg, {})
        headlines = seg_data.get("top_headlines", [])
        open_pos = positions.get("open_positions", [])
        conv = rec.get("conviction", 5)
        conv_color = self._conviction_color(conv)
        today = datetime.date.today().strftime("%d. %B %Y")
        high_vol = health.get("high_volatility_flag", False)

        headlines_html = "".join(
            f'<li style="margin:4px 0;font-size:13px;color:#374151;">{h}</li>'
            for h in headlines[:3]
        ) or "<li style='color:#9ca3af;font-size:13px;'>Keine aktuellen Schlagzeilen</li>"

        open_pos_html = ""
        if open_pos:
            pos_items = "".join(
                f'<li style="font-size:12px;color:#6b7280;">{p["symbol"]} — {p["type"].upper()} Strike {p["strike"]} exp {p["expiry"]}</li>'
                for p in open_pos[:5]
            )
            open_pos_html = f"""
            <div style="margin-top:16px;padding:12px;background:#fef9c3;border-radius:8px;">
              <p style="margin:0 0 6px;font-weight:600;font-size:13px;color:#854d0e;">Offene Positionen</p>
              <ul style="margin:0;padding-left:16px;">{pos_items}</ul>
            </div>"""

        high_vol_banner = ""
        if high_vol:
            high_vol_banner = """
            <div style="margin-bottom:16px;padding:10px 14px;background:#fef2f2;border-left:4px solid #dc2626;border-radius:4px;">
              <p style="margin:0;font-size:13px;color:#991b1b;font-weight:600;">⚠ HIGH VOLATILITY FLAG — Z-Score Ausreißer erkannt. Erhöhte Vorsicht.</p>
            </div>"""

        no_trade = ""
        if conv < self.cfg["thresholds"]["conviction_min_for_trade"]:
            no_trade = f"""
            <div style="margin-top:16px;padding:12px;background:#fef2f2;border-radius:8px;text-align:center;">
              <p style="margin:0;font-weight:700;color:#dc2626;">Conviction {conv}/10 — KEIN TRADE EMPFOHLEN</p>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Screener — {today}</title>
</head>
<body style="margin:0;padding:16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f9fafb;color:#111827;">

<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">

  <!-- Header -->
  <div style="background:{conv_color};padding:20px 24px;">
    <p style="margin:0;font-size:12px;color:rgba(255,255,255,0.8);text-transform:uppercase;letter-spacing:1px;">Commodity Options Screener</p>
    <h1 style="margin:4px 0 0;font-size:22px;font-weight:700;color:#fff;">{seg.upper()} — {rec.get('type','').upper()} Option</h1>
    <p style="margin:4px 0 0;font-size:13px;color:rgba(255,255,255,0.85);">{today}</p>
  </div>

  <div style="padding:20px 24px;">

    <!-- Data as-of notice -->
    <div style="margin-bottom:16px;padding:8px 12px;background:#f0f9ff;border-left:3px solid #0ea5e9;border-radius:4px;">
      <p style="margin:0;font-size:12px;color:#0369a1;">Analyse basiert auf US-Börsenschlusskursen vom Vortag. Handelsentscheidung bei Marktöffnung 15:30 CEST.</p>
    </div>

    {high_vol_banner}

    <!-- Main Recommendation -->
    <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:16px;">
      <p style="margin:0 0 4px;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Empfehlung</p>
      <p style="margin:0;font-size:20px;font-weight:700;color:#111827;font-family:monospace;">{rec.get('symbol','N/A')}</p>
      <div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap;">
        <span style="font-size:14px;color:#374151;">Strike: <strong>{rec.get('strike','N/A')}</strong></span>
        <span style="font-size:14px;color:#374151;">Expiry: <strong>{rec.get('expiry','N/A')}</strong></span>
        <span style="font-size:14px;color:#374151;">Typ: <strong>{rec.get('type','N/A').upper()}</strong></span>
      </div>
    </div>

    <!-- Conviction -->
    <div style="text-align:center;margin-bottom:16px;padding:14px;background:{conv_color}15;border-radius:8px;">
      <p style="margin:0;font-size:13px;color:#6b7280;">Conviction Score</p>
      <p style="margin:4px 0 0;font-size:36px;font-weight:800;color:{conv_color};">{conv}<span style="font-size:18px;">/10</span></p>
    </div>

    {no_trade}

    <!-- Metrics Grid -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
      <div style="background:#f8fafc;border-radius:8px;padding:12px;">
        <p style="margin:0;font-size:11px;color:#9ca3af;text-transform:uppercase;">Einstieg (Mid)</p>
        <p style="margin:4px 0 0;font-size:18px;font-weight:700;color:#111827;">${rec.get('mid_price',0):.2f}</p>
      </div>
      <div style="background:#f8fafc;border-radius:8px;padding:12px;">
        <p style="margin:0;font-size:11px;color:#9ca3af;text-transform:uppercase;">Fair Value (BS)</p>
        <p style="margin:4px 0 0;font-size:18px;font-weight:700;color:#111827;">${rec.get('fair_value_bs',0):.2f}</p>
      </div>
      <div style="background:#fef2f2;border-radius:8px;padding:12px;">
        <p style="margin:0;font-size:11px;color:#9ca3af;text-transform:uppercase;">Max. Verlust</p>
        <p style="margin:4px 0 0;font-size:18px;font-weight:700;color:#dc2626;">${rec.get('max_loss',0):.0f}</p>
      </div>
      <div style="background:#f0fdf4;border-radius:8px;padding:12px;">
        <p style="margin:0;font-size:11px;color:#9ca3af;text-transform:uppercase;">Expected Value (MC)</p>
        <p style="margin:4px 0 0;font-size:18px;font-weight:700;color:#16a34a;">${rec.get('mc_expected_value',0):.0f}</p>
      </div>
    </div>

    <!-- Scores -->
    <div style="background:#f8fafc;border-radius:8px;padding:14px;margin-bottom:16px;">
      <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#374151;text-transform:uppercase;">Modell-Scores</p>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
        <div style="text-align:center;">
          <p style="margin:0;font-size:11px;color:#9ca3af;">Edge Score</p>
          <p style="margin:2px 0 0;font-size:16px;font-weight:700;">{rec.get('edge_score',0):.0f}</p>
        </div>
        <div style="text-align:center;">
          <p style="margin:0;font-size:11px;color:#9ca3af;">Mirofish</p>
          <p style="margin:2px 0 0;font-size:16px;font-weight:700;">{rec.get('mirofish_score',0)}</p>
        </div>
        <div style="text-align:center;">
          <p style="margin:0;font-size:11px;color:#9ca3af;">Win-Rate hist.</p>
          <p style="margin:2px 0 0;font-size:16px;font-weight:700;">{rec.get('historical_win_rate',0)*100:.0f}%</p>
        </div>
      </div>
      <p style="margin:8px 0 0;font-size:11px;color:#9ca3af;text-align:center;">Win-Rate: spread-adjusted, as-of korrigiert (n={rec.get('sample_size',0)})</p>
    </div>

    <!-- Analysis -->
    <div style="margin-bottom:14px;">
      <p style="margin:0 0 6px;font-size:12px;font-weight:600;color:#374151;text-transform:uppercase;">These</p>
      <p style="margin:0;font-size:14px;color:#374151;line-height:1.5;">{rec.get('these','—')}</p>
    </div>
    <div style="margin-bottom:14px;">
      <p style="margin:0 0 6px;font-size:12px;font-weight:600;color:#dc2626;text-transform:uppercase;">Invalidierung</p>
      <p style="margin:0;font-size:14px;color:#374151;line-height:1.5;">{rec.get('invalidierung','—')}</p>
    </div>

    <!-- News -->
    <div style="background:#f8fafc;border-radius:8px;padding:14px;margin-bottom:16px;">
      <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#374151;text-transform:uppercase;">Aktuelle Schlagzeilen</p>
      <ul style="margin:0;padding-left:16px;">{headlines_html}</ul>
      <p style="margin:8px 0 0;font-size:12px;color:#6b7280;font-style:italic;">{rec.get('news_context','')}</p>
    </div>

    {open_pos_html}

    <!-- Footer -->
    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:11px;color:#9ca3af;">Data-Health-Score: {health.get('score',0):.1f}/100 | Mirofish: {rec.get('mirofish_confidence','none')} | OI: {rec.get('oi',0):,}</p>
      <p style="margin:6px 0 0;font-size:11px;color:#dc2626;font-weight:500;">DISCLAIMER: Diese Analyse ist keine Anlageberatung. Alle Angaben ohne Gewähr. Optionshandel birgt das Risiko des Totalverlustes der eingesetzten Prämie. Daten basieren auf Vortagsschlusskursen.</p>
    </div>

  </div>
</div>
</body>
</html>"""
        return html

    def _error_card(self, message):
        return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#fef2f2;padding:20px;border-radius:8px;">
<h2 style="color:#dc2626;">Screener Error</h2>
<p>{message}</p>
</div></body></html>"""
