"""
Commodity Options Screener v3.3 — BS+MC+Prophet integriert, echte Filter, DataHealthChecker
"""

import datetime
import json
import os
import time
import numpy as np
import pandas as pd
import yaml

from data_fetch import DataFetcher
from news_screener import NewsScreener
from analysis.haiku_preselect import HaikuPreselect
from analysis.mirofish_check import MirofishChecker
from analysis.claude_deep_analysis import ClaudeDeepAnalysis
from models.backtest_pandas import BacktestPandas
from models.black_scholes import BlackScholesCalculator
from models.monte_carlo import MonteCarloSimulator
from models.prophet_forecaster import ProphetForecaster
from preprocessing import DataHealthChecker
from html_card_generator import HTMLCardGenerator
from email_sender import EmailSender


LAST_RUN_PATH = "data/last_run.json"
RISK_FREE_RATE = 0.04
MAX_CANDIDATES_PER_SEGMENT = 80


def load_last_run():
    if os.path.exists(LAST_RUN_PATH):
        try:
            with open(LAST_RUN_PATH, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_last_run(artifact):
    def convert(obj):
        if isinstance(obj, (pd.Timestamp, datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, (bool,)):
            return bool(obj)
        if isinstance(obj, (int,)):
            return int(obj)
        if isinstance(obj, (float,)):
            return float(obj)
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(i) for i in obj]
        if isinstance(obj, set):
            return list(obj)
        return obj

    with open(LAST_RUN_PATH, "w") as f:
        json.dump(convert(artifact), f, indent=2)


def compute_hv(yf_data, ticker, window=20):
    """Historical realized volatility (annualized) from yfinance underlying data."""
    hv_key = f"{ticker}_hv20"
    if hv_key in yf_data:
        return float(yf_data[hv_key])

    ticker_data = yf_data.get(ticker, [])
    if not ticker_data:
        return 0.25

    try:
        closes = [float(r.get("Close", 0)) for r in ticker_data if r.get("Close", 0) > 0]
        if len(closes) < window + 1:
            return 0.25
        arr = np.array(closes[-(window + 1):])
        log_returns = np.log(arr[1:] / arr[:-1])
        hv = float(log_returns.std() * np.sqrt(252))
        return max(hv, 0.05)
    except:
        return 0.25


def run_pipeline():
    start_time = time.time()
    artifact = {"errors": [], "runtime_seconds": 0}

    try:
        print("=============================================================")
        print("Commodity Options Screener v3.3")
        print(f"Run {datetime.datetime.now(datetime.timezone.utc).isoformat()}Z")
        print("=============================================================")

        if os.path.exists("config.yaml"):
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            print("  ✅ config.yaml geladen")
        else:
            cfg = {}
            print("  ⚠️ config.yaml nicht gefunden")

        thr = cfg.get("thresholds", {})
        dte_min      = thr.get("options_dte_min", 21)
        dte_max      = thr.get("options_dte_max", 180)
        delta_min    = thr.get("options_delta_min", 0.20)
        delta_max    = thr.get("options_delta_max", 0.45)
        oi_min       = thr.get("options_oi_min", 100)
        ba_max       = thr.get("options_bid_ask_max_pct", 0.25)
        health_min   = thr.get("data_health_min", 55)
        seg_min      = thr.get("segment_score_min", 4)

        # Stage 1
        print("Stage 1: Fetching data...")
        fetcher = DataFetcher(cfg)
        raw_data = fetcher.fetch_all()
        print(f"  Sources: {list(raw_data.keys())}")

        # Stage 2 — real DataHealthChecker
        print("Stage 2: Data health check...")
        checker = DataHealthChecker(cfg)
        health_result = checker.compute(raw_data)
        health_score = health_result["score"]
        print(f"  Health score: {health_score:.1f}/100")
        if health_score < health_min:
            print(f"  ❌ Health {health_score} < {health_min} → abort")
            save_last_run(artifact)
            return True

        # Stage 3
        print("Stage 3: News screening...")
        screener = NewsScreener(cfg)
        segment_scores = screener.score_all_segments()
        qualifying_segments = [
            seg for seg, s in segment_scores.items()
            if s.get("total_score", 0) >= seg_min
        ]
        print(f"  Qualifying segments (score≥{seg_min}): {qualifying_segments}")

        if not qualifying_segments:
            print("  No qualifying segments → no trade today")
            save_last_run(artifact)
            return True

        # Stage 4 — Quantitative models: BS (HV-based) + MC + Prophet
        print("Stage 4: Quantitative models (BS/HV + MC + Prophet + filter)...")
        bs_calc  = BlackScholesCalculator(cfg)
        mc_sim   = MonteCarloSimulator(cfg)
        prophet  = ProphetForecaster(cfg, raw_data)
        backtester = BacktestPandas()

        yf_data = raw_data.get("yfinance", {})
        all_candidates = []

        for seg in qualifying_segments:
            seg_cfg = cfg.get("watchlist", {}).get(seg, {})
            ticker = seg_cfg.get("tickers", [None])[0]
            if not ticker:
                continue
            spot = raw_data.get("spot_prices", {}).get(ticker, 0.0)
            if spot <= 0:
                print(f"  WARNING: No spot price for {ticker}")
                continue

            # Historical volatility from underlying (not circular market IV)
            hv = compute_hv(yf_data, ticker, window=20)
            smile_factor = seg_cfg.get("smile_factor", 0.15)

            # Prophet drift for MC drift parameter
            prophet_result = prophet.forecast(seg)
            drift    = prophet_result.get("drift", 0.0)
            prop_dir = prophet_result.get("direction", "neutral")

            cot_data   = raw_data.get("cot", {}).get(ticker, {})
            cot_strength = cot_data.get("strength_score", 1.0)
            cot_z      = cot_data.get("z_score", 0.0)
            print(f"  [{seg}] {ticker} | Spot ${spot:.2f} | HV={hv:.1%} | COT={cot_data.get('signal_strength')} z={cot_z:.2f} | Prophet={prop_dir}")

            chains = raw_data.get("options_chains", {}).get(ticker, [])
            accepted = 0

            for opt in chains[:MAX_CANDIDATES_PER_SEGMENT]:
                try:
                    symbol = opt.get("symbol", "")
                    if not symbol:
                        continue

                    # --- Config-based filters (P1 #2) ---
                    dte = int(opt.get("days_to_expiration", 0) or 0)
                    if not (dte_min <= dte <= dte_max):
                        continue

                    delta_raw = abs(float(opt.get("delta", 0) or 0))
                    if not (delta_min <= delta_raw <= delta_max):
                        continue

                    oi = int(opt.get("open_interest", 0) or 0)
                    if oi < oi_min:
                        continue

                    bid = float(opt.get("bid", 0) or 0)
                    ask = float(opt.get("ask", 0) or 0)
                    if bid > 0 and ask > 0:
                        mid_price = (bid + ask) / 2
                        spread_pct = (ask - bid) / ask if ask > 0 else 1.0
                        if spread_pct > ba_max:
                            continue
                    else:
                        mid_price = float(opt.get("last", 0) or 0)
                    if mid_price <= 0:
                        continue

                    strike   = float(opt.get("strike", 0))
                    opt_type = opt.get("option_type", "call").lower()
                    T        = dte / 365.0
                    expiry_date = (
                        datetime.datetime.now(datetime.timezone.utc)
                        + datetime.timedelta(days=dte)
                    ).strftime("%Y-%m-%d")

                    # --- Black-Scholes with HV (not circular market IV) ---
                    sigma_adj = bs_calc.smile_adjusted_iv(hv, spot, strike, smile_factor)
                    fv_bs     = bs_calc.fair_value(spot, strike, r=RISK_FREE_RATE,
                                                   T=T, sigma=sigma_adj, option_type=opt_type)
                    greeks    = bs_calc.greeks(spot, strike, r=RISK_FREE_RATE,
                                               T=T, sigma=sigma_adj, option_type=opt_type)

                    # Positive bs_edge = option cheap vs. HV-implied fair value
                    bs_edge = (fv_bs - mid_price) / mid_price if mid_price > 0 else 0.0

                    # --- Monte Carlo EV ---
                    mc_ev, mc_win_prob = mc_sim.simulate(
                        spot=spot, strike=strike, r=RISK_FREE_RATE, T=T,
                        sigma=sigma_adj, premium=mid_price,
                        drift=drift, option_type=opt_type
                    )

                    # IV rank: market_iv / HV ratio → approximate rank 0-100
                    market_iv = float(opt.get("implied_volatility", hv) or hv)
                    iv_rank = min(100, max(0, int((market_iv / hv - 0.7) / 0.6 * 100))) if hv > 0 else 50

                    # --- Backtest on underlying history ---
                    underlying_history = yf_data.get(ticker, [])
                    bt = backtester.find_similar_real({
                        "symbol": symbol, "spot": spot, "strike": strike,
                        "dte": dte, "option_type": opt_type, "mid_price": mid_price,
                        "underlying_history": underlying_history,
                    })

                    # --- Combined edge score ---
                    cot_component  = cot_strength * 20          # 0–50
                    bs_component   = max(0.0, bs_edge * 100)    # 0–∞, 0 if overvalued
                    mc_component   = max(0.0, mc_ev / 5.0)      # scaled
                    hist_component = bt.get("win_rate", 0.48) * 20

                    edge_score = (
                        0.35 * cot_component +
                        0.35 * bs_component +
                        0.20 * mc_component +
                        0.10 * hist_component
                    )

                    all_candidates.append({
                        "symbol":           symbol,
                        "segment":          seg,
                        "ticker":           ticker,
                        "strike":           strike,
                        "dte":              dte,
                        "expiry":           expiry_date,
                        "spot":             spot,
                        "type":             opt_type,
                        "option_type":      opt_type,
                        "delta":            greeks["delta"],
                        "mid_price":        mid_price,
                        "fair_value_bs":    round(fv_bs, 3),
                        "bs_edge":          round(bs_edge, 4),
                        "oi":               oi,
                        "iv_pct":           round(market_iv * 100, 1),
                        "hv_pct":           round(hv * 100, 1),
                        "iv_rank":          iv_rank,
                        "mc_ev":            mc_ev,
                        "mc_win_prob":      mc_win_prob,
                        "hist_win_rate":    bt.get("win_rate", 0.48),
                        "hist_sample_size": bt.get("n", 0),
                        "mirofish_score":   edge_score,
                        "edge_score":       edge_score,
                        "cot_strength":     cot_strength,
                        "cot_z":            cot_z,
                        "prophet_drift":    drift,
                        "prophet_direction": prop_dir,
                    })
                    accepted += 1

                except Exception:
                    continue

            print(f"  [{seg}] {len(chains[:MAX_CANDIDATES_PER_SEGMENT])} geprüft → {accepted} Kandidaten nach Filtern")

        print(f"  Total candidates: {len(all_candidates)}")

        if not all_candidates:
            print("  No candidates after quantitative filter → no trade today")
            save_last_run(artifact)
            return True

        # Stage 5
        print("Stage 5: Haiku preselection...")
        haiku = HaikuPreselect(cfg)
        top20 = haiku.select(all_candidates, segment_scores)
        print(f"  Haiku selected: {len(top20)}")

        # Stage 6
        print("Stage 6: Mirofish filter...")
        miro = MirofishChecker(cfg)
        passed = miro.run(top20)
        print(f"  Mirofish passed: {len(passed)}")

        if not passed:
            print("  No candidates passed Mirofish → no trade today")
            save_last_run(artifact)
            return True

        # Stage 7 — raw_data injected so Claude gets real COT/EIA context
        print("Stage 7: Claude final analysis...")
        claude = ClaudeDeepAnalysis(cfg)
        enriched_context = dict(segment_scores)
        enriched_context["raw_data"] = raw_data
        recommendation = claude.analyze(finalists=passed, context=enriched_context)

        # Stage 8
        print("Stage 8: HTML card + email...")
        html_gen     = HTMLCardGenerator(cfg)
        email_sender = EmailSender(cfg)

        card = html_gen.generate(
            recommendation,
            segment_scores,
            health_result,
            {"open_positions": []}
        )
        email_sender.send(card, recommendation)

        artifact["recommendation"]    = recommendation
        artifact["health"]            = health_result
        artifact["candidates_total"]  = len(all_candidates)
        artifact["candidates_passed"] = len(passed)

    except Exception as e:
        import traceback
        print(f"PIPELINE ERROR: {e}")
        print(traceback.format_exc())
        artifact["errors"].append(str(e))

    finally:
        artifact["runtime_seconds"] = round(time.time() - start_time)
        save_last_run(artifact)
        print(f"Run complete in {artifact['runtime_seconds']}s")

    return True


if __name__ == "__main__":
    ok = run_pipeline()
    if not ok:
        exit(1)
