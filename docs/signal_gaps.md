# Signal Gaps — Priorisierte Lücken-Analyse

**Stand:** Mai 2026  
**Bezug:** Aktueller Screener v3.4 nach Stufen 0–10  
**Zweck:** Übersicht was fehlt, warum es relevant ist und was es kosten würde, es einzubauen.

---

## Kritische Lücken (vor Live Trading beheben)

### GAP-1: Roll Yield / Contango fehlt komplett

**Relevanz:** Strukturell zwingend.  
USO, UNG, CORN, WEAT, SOYB sind Futures-Roll-ETFs. In Contango-Märkten entstehen Rollkosten von 5–15 % p.a., die den ETF-Preis systematisch unter den Spot-Preis drücken. Das System handelt Optionen auf diese ETFs ohne zu wissen ob der Markt gerade in Contango oder Backwardation ist.

**Konsequenz ohne Fix:** Ein "bullisches" Setup auf UNG-Calls kann strukturell unprofitabel sein, weil UNG monatlich Wert durch den Roll verliert, auch wenn Natural Gas Spot steigt.

**Implementierung:**
- Tradier liefert bereits Futures-Expirations — Spot/Future-Spread berechnenbar
- Alternative: Quandl/CFTC Futures-Kurve für Front/2nd Month
- Signal: `roll_yield = (spot - future_price) / spot` → positiv = Backwardation (gut für Long), negativ = Contango (kostet)
- Integration: in `compute_macro_multiplier()` oder als separates Gate

**Aufwand:** M  
**Priorität:** 1 (vor Live Trading)

---

### GAP-2: Realzins-Signal verwendet Nominalzins (Proxy-Fehler)

**Relevanz:** Hoch für Metalle/Gold.  
`compute_macro_multiplier()` verwendet `DGS10` (10y Nominalzins). Dalios Framework und die empirische Literatur zeigen, dass der **Realzins** (10y TIPS, FRED: `DFII10`) der eigentliche Treiber für Gold und Edelmetalle ist. `DGS10 = Realzins + Inflationserwartung` — in inflationären Regimen unterschätzt `DGS10` den Commodity-Tailwind.

**Fix:**
```python
# data_fetch.py — fetch_fred() ergänzen:
"DFII10": "tips_10y",      # 10y TIPS Real Yield
"T5YIE":  "breakeven_5y",  # 5y Breakeven Inflation Rate
```

Integration in `compute_macro_multiplier()`:
```python
tips = fred.get("tips_10y", r10y)   # Fallback auf DGS10
if tips < 0 and seg == "metals":
    multiplier *= 1.12   # Negative Realzinsen = starker Metals-Tailwind
```

**Aufwand:** S  
**Priorität:** 1

---

### GAP-3: CPI abgerufen aber kein Signal

**Relevanz:** Mittel.  
`CPIAUCSL` wird in `fetch_fred()` abgerufen und im `raw_data["fred"]`-Dict gespeichert, aber in keiner Komponente des Edge-Scores oder Makro-Multipliers verwendet. Inflationsbeschleunigung ist ein Commodity-Tailwind.

**Fix:** In `compute_macro_multiplier()` ergänzen:
```python
cpi = fred.get("cpi", 0)
# YoY-Änderung erfordert 2 Datenpunkte — fetch_fred() muss limit=13 statt limit=2
if cpi_yoy > 4.0 and seg in ("energy", "metals"):
    multiplier *= 1.06
```

**Aufwand:** S  
**Priorität:** 2

---

## Mittelfristige Lücken (nach 3 Monaten Paper Trading)

### GAP-4: M2 Growth fehlt (Excess Liquidity Signal)

**Relevanz:** Mittel.  
`Excess Liquidity = M2 Growth (YoY) - CPI (YoY)` ist ein Vorlaufindikator für breite Asset-Inflation und Commodity-Nachfrage. FRED-Serie: `M2SL` (monatlich).

**Aufwand:** S (ein weiterer FRED-Abruf)  
**Priorität:** 3

---

### GAP-5: China Credit Impulse fehlt

**Relevanz:** Hoch für Industriemetalle (COPX), mittel für Energie.  
Credit Impulse ist der stärkste 6–24-Monats-Vorlaufindikator für Kupfer- und Industriemetall-Preise. China-TSF-Daten (Total Social Financing) über PBOC oder World Bank API erreichbar.

**Problem:** Daten sind quartalsweise, revisionsanfällig, Shadow-Banking-adjustierungen komplex.

**Realistische Alternative:** FRED-Serie `CRDQCNACABIS` (Credit to Private Non-Financial Sector, China, % of GDP, BIS). Quartalsweise, aber sauber.

**Aufwand:** M  
**Priorität:** 3

---

### GAP-6: Backtest ohne historische Optionspreise

**Relevanz:** Kritisch für Validität der Win-Rate.  
Der aktuelle Backtest simuliert ob der ETF-Preis den Breakeven überschritten hätte — ohne Theta-Decay, ohne historische Optionsprämien, ohne realistische Entry/Exit-Simulation.

**Fix-Optionen (aufsteigend nach Aufwand):**
1. **Tägliche IV-Aufzeichnung starten** (ab heute): Tradier IV täglich in `data/iv_history.parquet` speichern → in 6 Monaten echte Backtests möglich
2. **ORATS Historical Options** (~$50/Monat): vollständige historische Optionsdaten
3. **CBOE DataShop**: teurer, vollständiger

**Aufwand:** L (Datenbeschaffung) / S (tägliches Speichern als Sofortmaßnahme)  
**Priorität:** 2 — Sofortmaßnahme: IV täglich loggen

---

### GAP-7: Portfolio-Risikomanagement fehlt

**Relevanz:** Hoch vor Live Trading.  
Kein Exposure-Limit, keine Korrelationsanalyse zwischen offenen Positionen, kein Greeks-Aggregat.

Geplant als Stufe 8. Siehe [README.md Known Gaps](../README.md#known-gaps-see-audit-log).

**Aufwand:** M  
**Priorität:** 2

---

### GAP-11: ETF-Typ-spezifische Options-Eigenschaften nicht modelliert

**Relevanz:** Hoch — betrifft Grundannahmen des Systems.

Nicht alle Commodity-ETFs im Watchlist bieten dasselbe Risikoprofil für Long-Options:

| ETF-Typ | Hauptproblem für Long-Options | Konsequenz |
|---------|------------------------------|------------|
| USO, UNG | Roll Yield — Contango frisst systematisch Wert | Calls brauchen Backwardation oder starken Momentum |
| CORN, WEAT, SOYB | Starke Saisonalität, Roll Yield saisonabhängig | Calls nur in passender Jahreszeit (Ernte, Wetter) |
| GLD, SLV | Nah am Spot, kein Roll-Problem | Realzins + USD sind dominante Faktoren |
| XLE, COPX | Aktien-/Miners-Exposure, kein direkter Rohstoffpreis | Equity-Korrelation > Rohstoff-Korrelation; COT fast irrelevant |
| URA, URNM | Uran-Equity-Proxy, narrativgetrieben | Dünne Options-Ketten, hohe Spreads, aktienlastig |

**Was folgt daraus:**
- Für USO/UNG: Long Calls nur wenn Futures-Kurve in Backwardation oder Roll Yield neutral (GAP-1)
- Für XLE/COPX: COT-Gewichtung bereits auf 0.50/0.35 reduziert (Stufe 6), aber Equity-Beta nicht explizit kontrolliert
- Für URA/URNM: `options_oi_min` und `options_bid_ask_max_pct` sind die wichtigsten Filter — Liquiditäts-Gate

**Aufwand:** M (ETF-Typ-Klassifikation in config, segment-spezifische Gate-Logik)  
**Priorität:** 2

---

## Niedrigprioritäre Lücken (nice-to-have)

### GAP-8: Makro-Schwellenwerte nicht kalibriert

`compute_macro_multiplier()` verwendet Schwellenwerte ohne empirische Herleitung:
- `dxy > 125` → 0.88x
- `r10y > 4.5` → 0.92x (Metalle)

Diese Werte wurden nicht an historischen Returns kalibriert. Sensitivitätsanalyse ausstehend.

**Aufwand:** M | **Priorität:** 4

---

### GAP-9: American Options Pricing nicht implementiert

XLE (dividendenzahlend) und tiefe ITM-Puts sind anfällig für frühe Ausübung. Black-Scholes (European) unterschätzt den Wert systematisch.

Barone-Adesi-Whaley-Approximation würde reichen.

**Aufwand:** M | **Priorität:** 3

---

### GAP-10: Volatilitätsfläche fehlt

Smile-Approximation (`smile_factor` × moneyness²) ersetzt seit Stufe 2 keine Markt-IV mehr — Tradier liefert per-Strike-IV direkt. Aber keine Interpolation über Strikes/Expirations, kein Skew-Monitoring.

**Aufwand:** L | **Priorität:** 4

---

## Implementierungsreihenfolge (Empfehlung)

```
Sofort (< 1 Woche):
  GAP-2  TIPS-Realzins in fetch_fred() + compute_macro_multiplier()
  GAP-3  CPI als aktives Signal in compute_macro_multiplier()
  GAP-6  Tägliche IV-Aufzeichnung starten (Parquet-Log)

Nach 1 Monat Paper Trading:
  GAP-1  Roll Yield Signal (Tradier Futures-Curve)
  GAP-7  Portfolio-Risikomanagement (Stufe 8)

Nach 3 Monaten Paper Trading:
  GAP-4  M2 Growth / Excess Liquidity
  GAP-5  China Credit Impulse (FRED BIS-Daten)
  GAP-9  American Options Pricing

Langfristig:
  GAP-6  Echte Optionspreishistorien (ORATS o.ä.)
  GAP-8  Makro-Schwellenwerte kalibrieren
  GAP-10 Volatilitätsfläche
```
