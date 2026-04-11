"""
HTML Trading Card Generator v2 — optimized design
"""

import datetime


class HTMLCardGenerator:
    def __init__(self, cfg):
        self.cfg = cfg

    def _conv_color(self, score):
        if score >= 8: return "#16a34a"
        if score >= 6: return "#2563eb"
        if score >= 4: return "#d97706"
        return "#dc2626"

    def _direction_color(self, opt_type):
        return "#16a34a" if opt_type.lower() == "call" else "#dc2626"

    def generate(self, rec, seg_scores, health, positions):
        if not rec:
            return self._error_card("Keine Empfehlung generiert")

        seg       = rec.get("segment", "")
        seg_label = seg.replace("_", " ").upper()
        seg_data  = seg_scores.get(seg, {})
        headlines = seg_data.get("top_headlines", [])
        open_pos  = positions.get("open_positions", [])
        conv      = int(rec.get("conviction", 5))
        opt_type  = rec.get("type", "call").upper()
        conv_color   = self._conv_color(conv)
        dir_color    = self._direction_color(opt_type)
        today     = datetime.date.today().strftime("%d. %B %Y")
        high_vol  = health.get("high_volatility_flag", False)
        no_trade  = conv < self.cfg["thresholds"].get("conviction_min_for_trade", 6)

        mid   = rec.get("mid_price", 0)
        fv    = rec.get("fair_value_bs", 0)
        fv_vs = ((fv - mid) / mid * 100) if mid > 0 and fv > 0 else None
        if fv > 0 and fv_vs is not None and abs(fv_vs) < 50:
            fv_str = f"${fv:.2f}"
            fv_delta_str = f"{fv_vs:+.1f}% vs. Markt"
        else:
            fv_str = "n/a"
            fv_delta_str = "Smile-Korrektur unzureichend"

        mc_ev_raw = rec.get("mc_expected_value", 0)
        mc_ev_str = f"${mc_ev_raw:.0f}"

        max_loss  = round(mid * 100, 0)
        wr        = rec.get("historical_win_rate", 0)
        n         = rec.get("sample_size", 0)
        miro      = rec.get("mirofish_score", 0)
        miro_conf = rec.get("mirofish_confidence", "none")
        edge      = rec.get("edge_score", 0)

        headlines_html = ""
        for h in headlines[:3]:
            headlines_html += f'<li style="margin:6px 0;font-size:13px;color:#374151;line-height:1.4;">{h.capitalize()}</li>'
        if not headlines_html:
            headlines_html = '<li style="color:#9ca3af;font-size:13px;">Keine aktuellen Schlagzeilen</li>'

        open_pos_html = ""
        if open_pos:
            items = "".join(
                f'<div style="font-size:12px;color:#6b7280;padding:3px 0;">'
                f'{p["symbol"]} — {p.get("type","").upper()} Strike {p["strike"]} exp {p["expiry"]}</div>'
                for p in open_pos[:3]
            )
            open_pos_html = f"""
            <div style="margin-top:16px;padding:12px;background:#fef9c3;border-radius:8px;border-left:3px solid #ca8a04;">
              <p style="margin:0 0 6px;font-weight:600;font-size:12px;color:#854d0e;text-transform:uppercase;letter-spacing:0.5px;">Offene Positionen</p>
              {items}
            </div>"""

        high_vol_html = ""
        if high_vol:
            high_vol_html = """
            <div style="margin-bottom:12px;padding:10px 14px;background:#fef2f2;border-left:3px solid #dc2626;border-radius:0 4px 4px 0;">
              <p style="margin:0;font-size:12px;color:#991b1b;font-weight:600;">HIGH VOLATILITY FLAG — Z-Score Ausreisser erkannt</p>
            </div>"""

        no_trade_html = ""
        if no_trade:
            no_trade_html = f"""
            <div style="margin:16px 0;padding:14px;background:#fef2f2;border-radius:8px;border:1.5px solid #fca5a5;text-align:center;">
              <p style="margin:0 0 4px;font-size:11px;color:#991b1b;text-transform:uppercase;letter-spacing:1px;font-weight:600;">Conviction {conv}/10</p>
              <p style="margin:0;font-size:16px;font-weight:700;color:#dc2626;">KEIN TRADE EMPFOHLEN</p>
              <p style="margin:6px 0 0;font-size:12px;color:#991b1b;">Mindest-Conviction fuer Trades: {self.cfg["thresholds"].get("conviction_min_for_trade", 6)}/10</p>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Screener {today}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<div style="max-width:580px;margin:24px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

  <div style="background:#111827;padding:20px 24px 16px;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
      <div>
        <p style="margin:0;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:1.5px;">Commodity Options Screener</p>
        <h1 style="margin:4px 0 0;font-size:20px;font-weight:700;color:#ffffff;">{seg_label}</h1>
        <p style="margin:4px 0 0;font-size:13px;color:#6b7280;">{today}</p>
      </div>
      <div style="text-align:right;">
        <div style="display:inline-block;padding:5px 12px;background:{dir_color};border-radius:20px;">
          <span style="font-size:13px;font-weight:700;color:#ffffff;">{opt_type}</span>
        </div>
        <p style="margin:6px 0 0;font-size:11px;color:#6b7280;">Health {health.get('score',0):.0f}/100</p>
      </div>
    </div>
  </div>

  <div style="padding:8px 24px;background:#f8fafc;border-bottom:1px solid #e5e7eb;">
    <p style="margin:0;font-size:11px;color:#64748b;">Daten: US-Boersenschluss Vortag &nbsp;·&nbsp; Handelsentscheidung: US-Marktoeffnung 15:30 CEST</p>
  </div>

  <div style="padding:20px 24px;">
    {high_vol_html}

    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:16px;">
      <p style="margin:0 0 8px;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Empfehlung</p>
      <p style="margin:0;font-size:16px;font-weight:700;color:#111827;font-family:monospace;">{rec.get('symbol','N/A')}</p>
      <div style="display:flex;gap:20px;margin-top:10px;flex-wrap:wrap;">
        <div><p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">Strike</p><p style="margin:2px 0 0;font-size:15px;font-weight:600;color:#111827;">${rec.get('strike','N/A')}</p></div>
        <div><p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">Expiry</p><p style="margin:2px 0 0;font-size:15px;font-weight:600;color:#111827;">{rec.get('expiry','N/A')}</p></div>
        <div><p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">Typ</p><p style="margin:2px 0 0;font-size:15px;font-weight:600;color:{dir_color};">{opt_type}</p></div>
        <div><p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">Einstieg</p><p style="margin:2px 0 0;font-size:15px;font-weight:600;color:#111827;">${mid:.2f}</p></div>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;padding:14px 16px;background:{conv_color}18;border-radius:10px;border-left:3px solid {conv_color};">
      <div style="text-align:center;min-width:52px;">
        <p style="margin:0;font-size:30px;font-weight:800;color:{conv_color};line-height:1;">{conv}</p>
        <p style="margin:2px 0 0;font-size:11px;color:{conv_color};">/ 10</p>
      </div>
      <div>
        <p style="margin:0;font-size:11px;font-weight:600;color:{conv_color};text-transform:uppercase;letter-spacing:0.5px;">Conviction Score</p>
        <p style="margin:4px 0 0;font-size:13px;color:#374151;line-height:1.5;">{rec.get('these','—')}</p>
      </div>
    </div>

    {no_trade_html}

    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:16px;">
      <div style="background:#f8fafc;border-radius:8px;padding:12px;text-align:center;">
        <p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">Fair Value BS</p>
        <p style="margin:4px 0 0;font-size:15px;font-weight:700;color:#111827;">{fv_str}</p>
        <p style="margin:2px 0 0;font-size:10px;color:#6b7280;">{fv_delta_str}</p>
      </div>
      <div style="background:#fef2f2;border-radius:8px;padding:12px;text-align:center;">
        <p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">Max. Verlust</p>
        <p style="margin:4px 0 0;font-size:15px;font-weight:700;color:#dc2626;">${max_loss:.0f}</p>
        <p style="margin:2px 0 0;font-size:10px;color:#9ca3af;">Praemie x 100</p>
      </div>
      <div style="background:#f0fdf4;border-radius:8px;padding:12px;text-align:center;">
        <p style="margin:0;font-size:10px;color:#9ca3af;text-transform:uppercase;">MC Exp. Value</p>
        <p style="margin:4px 0 0;font-size:15px;font-weight:700;color:#16a34a;">{mc_ev_str}</p>
        <p style="margin:2px 0 0;font-size:10px;color:#9ca3af;">Monte Carlo</p>
      </div>
    </div>

    <div style="background:#f8fafc;border-radius:8px;padding:14px;margin-bottom:16px;">
      <p style="margin:0 0 10px;font-size:11px;font-weight:600;color:#374151;text-transform:uppercase;letter-spacing:0.5px;">Modell-Scores</p>
      <div style="display:flex;gap:8px;">
        <div style="flex:1;text-align:center;padding:10px 8px;background:#fff;border-radius:6px;border:1px solid #e5e7eb;">
          <p style="margin:0;font-size:10px;color:#9ca3af;">Edge Score</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#2563eb;">{edge:.0f}</p>
        </div>
        <div style="flex:1;text-align:center;padding:10px 8px;background:#fff;border-radius:6px;border:1px solid #e5e7eb;">
          <p style="margin:0;font-size:10px;color:#9ca3af;">Mirofish</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#7c3aed;">{miro}</p>
          <p style="margin:2px 0 0;font-size:10px;color:#9ca3af;">{miro_conf}</p>
        </div>
        <div style="flex:1;text-align:center;padding:10px 8px;background:#fff;border-radius:6px;border:1px solid #e5e7eb;">
          <p style="margin:0;font-size:10px;color:#9ca3af;">Win-Rate hist.</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#374151;">{wr*100:.0f}%</p>
          <p style="margin:2px 0 0;font-size:10px;color:#9ca3af;">n={n}</p>
        </div>
      </div>
      <p style="margin:8px 0 0;font-size:10px;color:#9ca3af;text-align:center;">spread-adjusted · as-of korrigiert · historisch</p>
    </div>

    <div style="margin-bottom:16px;padding:12px 14px;background:#fff7ed;border-left:3px solid #f97316;border-radius:0 8px 8px 0;">
      <p style="margin:0 0 4px;font-size:11px;font-weight:600;color:#c2410c;text-transform:uppercase;letter-spacing:0.5px;">Invalidierung</p>
      <p style="margin:0;font-size:13px;color:#374151;line-height:1.5;">{rec.get('invalidierung','—')}</p>
    </div>

    <div style="margin-bottom:16px;">
      <p style="margin:0 0 8px;font-size:11px;font-weight:600;color:#374151;text-transform:uppercase;letter-spacing:0.5px;">Aktuelle Schlagzeilen</p>
      <ul style="margin:0;padding-left:16px;">{headlines_html}</ul>
      <p style="margin:10px 0 0;font-size:13px;color:#6b7280;font-style:italic;line-height:1.5;">{rec.get('news_context','')}</p>
    </div>

    {open_pos_html}

    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #f3f4f6;">
      <p style="margin:0;font-size:11px;color:#9ca3af;">OI: {rec.get('oi',0):,} &nbsp;·&nbsp; Mirofish: {miro_conf} &nbsp;·&nbsp; v3.1</p>
      <p style="margin:8px 0 0;font-size:11px;color:#ef4444;line-height:1.5;">Keine Anlageberatung. Optionshandel birgt das Risiko des Totalverlustes der eingesetzten Praemie. Daten basieren auf Vortagsschlusskursen.</p>
    </div>

  </div>
</div>
</body>
</html>"""
        return html

    def _error_card(self, message):
        return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:20px;background:#f3f4f6;">
<div style="max-width:580px;margin:0 auto;background:#fff;padding:24px;border-radius:12px;">
<h2 style="color:#dc2626;margin:0 0 8px;">Screener Fehler</h2>
<p style="color:#374151;">{message}</p>
</div></body></html>"""
