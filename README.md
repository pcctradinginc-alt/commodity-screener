# Commodity Options Screener v3.1

Automated daily commodity options screener running on GitHub Actions.
Analyzes Energie, Agrar, Metalle and Equity-Proxies and delivers one
concrete options recommendation via Gmail every trading morning.

## Pipeline

```
GitHub Actions Cron (08:00 CEST, Mo–Fr)
  → Stage 1: Data Fetch (Tradier, Finnhub, EIA, COT, FRED, News)
  → Stage 2: Data Health Score (gate ≥ 75)
  → Stage 3: News Screener (keyword scoring, segment ranking)
  → Stage 4: Quantitative Models (Prophet, Black-Scholes, Monte Carlo, Backtest)
  → Stage 5: Claude Haiku Preselection (Top-20)
  → Stage 6: Mirofish Agent Simulation (gate > 65)
  → Stage 7: Claude Opus Final Analysis
  → Stage 8: HTML Trading Card → Gmail
```

## Setup

### 1. Fork / clone this repo (keep Private)

### 2. Set GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Description |
|--------|-------------|
| `CLAUDE_API_KEY` | Anthropic API key |
| `TRADIER_KEY` | Tradier Bearer token (full API) |
| `FINNHUB_KEY` | Finnhub API key (free tier) |
| `EIA_KEY` | EIA Open Data API key (free) |
| `FRED_KEY` | FRED API key (free) |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your main password) |

### 3. Configure recipients

Edit `config.yaml`:
```yaml
email:
  recipients:
    - your@email.com
```

### 4. First test run

Go to **Actions → Daily Commodity Options Screener → Run workflow**

Check the run log and confirm you receive the email.

## API Keys (all free)

- **EIA**: https://www.eia.gov/opendata/register.php
- **FRED**: https://fred.stlouisfed.org/docs/api/api_key.html
- **Finnhub**: https://finnhub.io (free tier)
- **Anthropic**: https://console.anthropic.com

## Costs

| Service | Monthly cost |
|---------|-------------|
| Claude Haiku | ~$0.02–0.05 |
| Claude Opus | ~$0.50–1.50 |
| Everything else | Free |
| **Total** | **~$0.55–1.55/month** |

## Positions Tracking

`data/positions.json` tracks open and closed positions.
After each run, GitHub Actions commits any changes automatically.
You must manually confirm whether you actually entered a trade.

## Disclaimer

This system provides analysis, not investment advice.
Options trading involves risk of total loss of premium paid.
All data is based on prior day closing prices.
