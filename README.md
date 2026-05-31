# Commodity ETF Options Screener v3.4

Automated daily screener for options on **commodity ETFs**, running on GitHub Actions.
Screens four segments (Energy, Agriculture, Metals, Nuclear) and delivers one
concrete options recommendation via Gmail every trading morning.

## Instrument Definition

This system trades **American-style options on commodity ETFs**, not futures options.

| Property | Value |
|----------|-------|
| Instrument | Listed equity options on ETFs |
| Exercise style | American (early exercise possible) |
| Settlement | Cash / shares (no physical delivery) |
| Contract size | 100 shares per contract |
| Underlying | ETF price (not futures curve) |
| Exchanges | CBOE, NYSE Arca (via Tradier) |

**Segments and ETFs:**

| Segment | Tickers | Underlying exposure |
|---------|---------|---------------------|
| Energy | USO, XLE, UNG | WTI crude oil futures, oil equities, natural gas futures |
| Agriculture | CORN, WEAT, SOYB | Corn, wheat, soybean futures (rolling) |
| Metals | GLD, SLV, COPX | Gold, silver, copper miners |
| Nuclear | URA, URNM | Uranium equities (no listed options on U3O8 spot) |

**Known limitations of this instrument choice vs. direct futures options:**
- ETFs carry roll costs (contango drag) not visible in spot price
- COT signals describe futures positioning, not ETF flows — used as proxy only
- No leverage beyond ETF structure; futures options would offer higher notional exposure
- XLE pays dividends — early exercise of deep ITM puts is a real risk (not modeled in v3.4)

## Pipeline

```
GitHub Actions Cron (06:00 UTC = 08:00 CEST, Mo–Fr)
  → Stage 1: Data Fetch (Tradier options chains + spot, Finnhub, yfinance, EIA, FRED, COT)
  → Stage 2: Data Health Score (gate ≥ 55/100)
  → Stage 3: News Screener (FinBERT sentiment + keyword scoring, gate ≥ 4/10 per segment)
  → Stage 4: Quantitative Models (Black-Scholes HV-fair-value, Monte Carlo GBM, Prophet, Backtest)
  → Stage 5: Claude Haiku Preselection (top 20 by edge score)
  → Stage 6: Mirofish Gate (edge_score ≥ 18)
  → Stage 7: Claude Opus Final Analysis (conviction score + trade card text)
  → Stage 8: HTML Trading Card → Gmail
```

## Model Assumptions (v3.4)

| Component | Current approach | Known limitation |
|-----------|-----------------|-----------------|
| Options pricing | Black-Scholes (European) with HV as sigma | American exercise not modeled; HV ≠ market IV |
| Volatility | 20-day realized HV from yfinance | No vol surface; smile approximated by fixed factor |
| Backtest | Rolling window on underlying price history | No historical option prices; theta decay not simulated |
| Risk-free rate | FRED FEDFUNDS (dynamic, fallback 4%) | Daily rate, not term-structure |
| COT signal | CFTC futures positioning as proxy | Futures ≠ ETF; no direct ETF flow data |
| Contract size | 100 (hardcoded, correct for ETF options) | Must change if extended to futures options |

## Setup

### 1. Fork / clone this repo (keep Private)

### 2. Set GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Description |
|--------|-------------|
| `CLAUDE_API_KEY` | Anthropic API key |
| `TRADIER_KEY` | Tradier Bearer token (full API, not sandbox) |
| `FINNHUB_KEY` | Finnhub API key (free tier) |
| `EIA_KEY` | EIA Open Data API key (free) |
| `FRED_KEY` | FRED API key (free) |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your account password) |
| `RECIPIENT_EMAIL` | Email address to receive trading cards |

### 3. First test run

Go to **Actions → Daily Commodity Options Screener → Run workflow**

Check the run log and confirm you receive the email.

## API Keys (all free)

- **EIA**: https://www.eia.gov/opendata/register.php
- **FRED**: https://fred.stlouisfed.org/docs/api/api_key.html
- **Finnhub**: https://finnhub.io (free tier)
- **Tradier**: https://developer.tradier.com (brokerage account required for live data)
- **Anthropic**: https://console.anthropic.com

## Monthly Costs

| Service | Monthly cost |
|---------|-------------|
| Claude Haiku | ~$0.02–0.05 |
| Claude Opus | ~$0.50–1.50 |
| Everything else | Free |
| **Total** | **~$0.55–1.55/month** |

## Positions Tracking

`data/positions.json` tracks open and closed positions.
After each run, GitHub Actions commits any changes automatically.
**You must manually confirm whether you actually entered a trade.**
The system generates recommendations only — it does not execute orders.

## Known Gaps (see audit log)

These are documented limitations to address before live trading:

1. **Backtest**: uses underlying price history, not historical option prices — win-rate is approximate
2. **Pricing**: Black-Scholes with HV; market IV used for filtering only, not for fair value
3. **American exercise**: XLE dividend risk not modeled; deep ITM puts may show incorrect fair value
4. **COT-ETF mismatch**: COT signals are futures-based proxies, not direct ETF positioning data
5. **No portfolio risk model**: no cross-position Greeks aggregation or exposure limits

## Disclaimer

This system provides analysis, not investment advice.
Options trading involves significant risk including total loss of premium paid.
ETF options are subject to early exercise; verify contract specifications before trading.
OCC and FINRA note that options are not suitable for all investors.
Past backtest results do not guarantee future performance.
