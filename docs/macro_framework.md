# Makro-Framework: Ray Dalios Commodity-Zyklen-These

**Stand:** Mai 2026  
**Zweck:** Theoretische Grundlage für die Makro-Signale im Screener. Dokumentiert was die Signale in `compute_macro_multiplier()` und `fetch_fred()` begründet, welche Teile der These bereits implementiert sind und welche fehlen.

---

## 1. Dalios Kern-These

Dalio betrachtet Commodity-Zyklen nicht als primär physische Supercycles, sondern als Reaktion auf monetäre und kreditgetriebene Faktoren. Grundformel:

```
P = Total Spending (Money + Credit) / Supply
```

Ein physisches Angebotsdefizit von 1–2 % kann durch Kreditexpansion vollständig überlagert werden. Commodity-Bullenmärkte entstehen fast immer parallel zu Credit-Booms.

**Hauptaussagen:**
- Im späten Stadium des langfristigen Debt-Cycle (Monetary Debasement → Inflation) outperformen harte Assets (Commodities + Gold) gegenüber Finanzassets
- Niedrige Realzinsen senken Lagerhaltungskosten (Cost-of-Carry) → steigende Spot-Preise
- Breite Commodity-Exposition ist ein Inflations-Hedge (Dalio: ~7.5 % im All Weather Portfolio)

---

## 2. Empirische Evidenz

| Studie | Befund | Einschränkung |
|--------|--------|--------------|
| Anzuini et al. (ECB 2010, IJCB 2013) | 100 bp US-Lockerung → +4–7 % breiter Commodity-Index (Peak-Effekt) | Nur US-Geldpolitik |
| Miranda-Pinto et al. (IMF WP 2023) | 10 bp Zinsanstieg → -0.5–2.5 % Commodity-Preise; erklärt bis zu 47 % des Inflationseffekts der US-Geldpolitik | US-spezifisch |
| Frankel (NBER 12713, 2006) | Niedrige Realzinsen treiben Commodity-Preise durch Cost-of-Carry-Kanal | Strukturelle Annahmen |
| World Bank Commodity Cycle Studies (Kabundi & Zahid) | Monetäre Faktoren erklären signifikante, aber moderate Anteile | Nicht „overwhelming" |

**Evidenzurteil:** Monetäre Faktoren sind ein robuster Erklärungsfaktor, aber nicht dominant. Physische Angebots- und Nachfragedynamiken bleiben primär für kurzfristige Bewegungen.

---

## 3. Signal-Hierarchie nach Rohstoffgruppe

| Rohstoffgruppe | Primärtreiber | Sekundärsignal |
|----------------|--------------|----------------|
| Kupfer, Aluminium, Industriemetalle | China Credit Impulse + globaler PMI + USD | Futures-Kurvenstruktur |
| Öl | Globale Nachfrage + OPEC + Geopolitik | Roll Yield / Contango |
| Gold | Realzinsen + USD + Zentralbankkäufe | Risikoaversion |
| Agrar | Wetter + Lager + Saisonalität | Energiepreise |
| Gas | Regionale Lager + LNG-Flüsse | Wetter + Infrastruktur |

---

## 4. Relevante Kennzahlen

### Credit Impulse (wichtigster Vorlaufindikator für Industriemetalle)

```
CI_t = (ΔCredit_{t-12..t} / GDP_t) - (ΔCredit_{t-24..t-12} / GDP_{t-12})
```

Lead-Time: 6–24 Monate. Quellen: PBOC TSF (Total Social Financing), BIS, FRED.  
**Problem:** Revisionsanfällig, quartalsweise, China-Daten enthalten Shadow-Banking/LGFV.

### Realzins (primärer Gold/Metall-Treiber)

```
Real Rate = 10y TIPS Yield   (besser als: 10y Nominal - Breakeven)
```

FRED-Serie: `DFII10` (10-Year Treasury Inflation-Indexed Security).  
Lead-Time: 3–9 Monate.

### Futures Cost-of-Carry

```
F = S × e^((r + u - y) × T)
```

- `r` = Realzins (Finanzierungskosten)
- `u` = Storage Cost
- `y` = Convenience Yield
- Roll Yield ≈ `(Spot - Future) / Spot` — positiv in Backwardation, negativ in Contango

### M2 Growth vs. Inflation

```
Excess Liquidity = M2 Growth (YoY) - CPI (YoY)
```

Positiv → Geldmenge wächst schneller als Inflation → Liquiditätsüberschuss stützt Asset-Preise.  
FRED-Serien: `M2SL` (M2), `CPIAUCSL` (CPI).

---

## 5. Verbessertes Scoring-Modell (Referenz für zukünftige Implementierung)

```
Score_t = 0.35 × CI_China_{t-6..12}
        + 0.25 × RealRateSignal_t
        + 0.20 × USDSignal_t
        + 0.20 × TrendSignal_t
```

Positionslogik:

```python
if macro_score > 70 and trend_score > 0 and curve_signal >= 0:  # kein starkes Contango
    position = risk_scaled_long      # +1.0 bis +2.0 (vol-adjustiert)
elif macro_score < 35 or real_rates_breakout:
    position = 0                     # neutral / cash
else:
    position = reduced_neutral       # 0 bis +0.5
```

---

## 6. Kritische Einschränkungen

**Konzeptioneller Hauptfehler** bei der Anwendung der Dalio-These als Trading-System:  
Vermischung von (1) Makro-Erklärung, (2) Prognosemodell und (3) profitablem Trading-System. Nur (1) ist empirisch robust.

| Behauptung | Korrekte Einschätzung |
|------------|----------------------|
| „Macro-Hedgefonds setzen das erfolgreich um" | Zu pauschal; unbekannte Drawdowns |
| „Monetäre Shocks erklären 20–50 %" | Peak-Effekt realistisch 4–7 % |
| „Sharpe > 0.8 seit 1990s" | Nicht belegt ohne vollständigen OOS-Backtest |
| „Credit Impulse ist wichtigster Indikator" | Nur für Industriemetalle robust; schwächer für Energie |
| „M2 – CPI als Total-Spending-Proxy" | Ignoriert Velocity, Dollar-Liquidität, internationale Flows |

**Roll Yield ist nicht optional.** ETFs wie USO, UNG, CORN tragen Futures-Roll-Kosten von strukturell 5–15 % p.a. in Contango-Märkten. Ein System das Roll Yield ignoriert, rechnet mit einem systematisch verzerrten Underlying.

---

## 7. Status im aktuellen Screener

Siehe [`docs/signal_gaps.md`](signal_gaps.md) für vollständige Gap-Analyse und Prioritäten.

| Signal | Dalio-Relevanz | Implementiert |
|--------|---------------|--------------|
| USD (DTWEXBGS) | ✅ mittel | ✅ `compute_macro_multiplier()` |
| 10y Nominalzins (DGS10) | ✅ mittel | ✅ als Proxy für Realzins |
| 10y TIPS Realzins (DFII10) | ✅ hoch | ❌ DGS10 ist Proxy, nicht TIPS |
| Fed Funds Rate | ✅ mittel | ✅ für `risk_free_rate` |
| CPI (CPIAUCSL) | ✅ mittel | ⚠️ abgerufen, aber kein Signal |
| M2 Growth (M2SL) | ✅ mittel | ❌ nicht abgerufen |
| China Credit Impulse | ✅ hoch für Metalle | ❌ nicht abgerufen |
| Roll Yield / Contango | ✅ strukturell zwingend | ❌ fehlt komplett |
| Excess Liquidity (M2-CPI) | ✅ mittel | ❌ CPI da, M2 fehlt |
