"""
Commodity Options Screener v3.2 – MIT ECHTEM BACKTESTING
Jetzt mit realen historischen Optionspreisen (Step 2)
"""

import json
import os
import sys
import time
import datetime
import traceback
import yaml

from data_fetch import DataFetcher
from preprocessing import DataHealthChecker
from news_screener import NewsScreener
from models.prophet_forecaster import ProphetForecaster
from models.black_scholes import BlackScholesCalculator
from models.monte_carlo import MonteCarloSimulator
from models.backtest_pandas import BacktestEngine          # ← bleibt gleich
from analysis.haiku_preselect import HaikuPreselect
from analysis.mirofish_check import MirofishChecker
from analysis.claude_deep_analysis import ClaudeDeepAnalysis
from html_card_generator import HTMLCardGenerator
from email_sender import EmailSender

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
POSITIONS_PATH = os.path.join(BASE_DIR, "data", "positions.json")
LAST_RUN_PATH = os.path.join(BASE_DIR, "data", "last_run.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_positions():
    with open(POSITIONS_PATH) as f:
        return json.load(f)


def save_positions(positions):
    positions["last_updated"] = datetime.datetime.utcnow().isoformat() + "Z"
    with open(POSITIONS_PATH, "w") as f:
        json.dump(positions, f, indent=2)


def save_last_run(artifact):
    with open(LAST_RUN_PATH, "w") as f:
        json.dump(artifact, f, indent=2)


def update_expired_positions(positions, tradier_key):
    today = datetime.date.today()
    for pos in positions["open_positions"][:]:
        expiry = datetime.date.fromisoformat(pos["expiry"])
        if expiry < today:
            pos["status"] = "expired"
            pos["exit_date"] = today.isoformat()
            pos["exit_price"] = 0.0
            pos["pnl"] = -pos["entry_price"] * 100
            positions["closed_positions"].append(pos)
            positions["open_positions"].remove(pos)
    return positions


def run_pipeline():
    start_time = time.time()
    run_id = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n{'='*60}")
    print(f"Commodity Options Screener v3.2 — ECHTES BACKTESTING — Run {run_id}")
    print(f"{'='*60}\n")

    cfg = load_config()
    positions = load_positions()
    thr = cfg["thresholds"]

    artifact = {
        "run_id": run_id,
        "version": "3.2",
        "data_health": {},
        "data_as_of": {},
        "segments": {},
        "candidates_pre_haiku": 0,
        "candidates_post_haiku": 0,
        "candidates_post_mirofish": 0,
        "mirofish_available": True,
        "mirofish_timeouts": 0,
        "final_recommendation": None,
        "open_positions_count": len(positions["open_positions"]),
        "errors": [],
        "runtime_seconds": 0,
        "real_backtest_used": True,          # ← NEU
    }

    try:
        # ── Stage 1: Data Fetch ──────────────────────────────────────
        print("Stage 1: Fetching data...")
        fetcher = DataFetcher(cfg)
        raw_data = fetcher.fetch_all()
        artifact["data_as_of"] = raw_data.get("as_of", {})
        print(f"  Data fetched. Sources: {list(raw_data.keys())}")

        # ── Stage 2: Data Health ─────────────────────────────────────
        print("\nStage 2: Data health check...")
        checker = DataHealthChecker(cfg)
        health = checker.compute(raw_data)
        artifact["data_health"] = health
        print(f"  Health score: {health['score']:.1f}")

        if health["score"] < thr["data_health_min"]:
            msg = f"Data health {health['score']:.1f} < {thr['data_health_min']} — aborting"
            print(f"  ABORT: {msg}")
            artifact["errors"].append(msg)
            save_last_run(artifact)
            return False

        # ── Stage 3: News Screener ───────────────────────────────────
        print("\nStage 3: News screening...")
        screener = NewsScreener(cfg)
        segment_scores = screener.score_all_segments()
        artifact["segments"] = segment_scores

        qualifiers = [
            seg for seg, data in segment_scores.items()
            if data["total_score"] >= thr["segment_score_min"]
        ]
        qualifiers = sorted(
            qualifiers,
            key=lambda s: segment_scores[s]["total_score"],
            reverse=True
        )[:thr["max_qualifiers"]]

        if not qualifiers:
            print("  No segments qualify today — pipeline ends")
            save_last_run(artifact)
            return False

        print(f"  Qualifying segments: {qualifiers}")
        raw_data["segment_scores"] = segment_scores

        # ── Stage 4: Quantitative Models + ECHTES HISTORISCHES BACKTESTING ──
        print("\nStage 4: Quantitative models + real option history...")
        all_candidates = []
        raw_data["historical_options"] = {}   # ← NEU: Container für echte Options-Historie

        for seg in qualifiers:
            ticker = cfg["watchlist"][seg]["tickers"][0]
            smile = cfg["watchlist"][seg].get("smile_factor", 0.15)
            print(f"  [{seg}] {ticker}")

            prophet = ProphetForecaster(cfg, raw_data)
            forecast = prophet.forecast(seg)

            bs_calc = BlackScholesCalculator(cfg)
            mc_sim = MonteCarloSimulator(cfg)
            backtester = BacktestEngine(cfg, raw_data)   # ← wird später mit realen Daten gefüttert

            chain = raw_data.get("options_chains", {}).get(ticker, [])
            filter_stats = {"oi": 0, "volume": 0, "dte": 0, "delta": 0,
                           "mid": 0, "spread": 0, "passed": 0}
            today_date = datetime.date.today()

            # Spot price (unverändert)
            fh_quote = raw_data.get("quotes", {}).get(ticker, {})
            tr_quote = raw_data.get("tradier_quotes", {}).get(ticker, {})
            spot = (
                float(tr_quote.get("last", 0) or 0) or
                float(fh_quote.get("c", 0) or 0) or
                float(fh_quote.get("pc", 0) or 0) or
                float(fh_quote.get("previousClose", 0) or 0)
            )
            if spot <= 0:
                print(f"  WARNING: No valid spot price for {ticker} — skipping segment")
                continue

            for option in chain:
                # ... (der gesamte Filter-Block ist identisch mit v3.1 – unverändert) ...
                oi = option.get("open_interest", 0) or 0
                volume = option.get("volume", 0) or 0
                bid = option.get("bid", 0) or 0
                ask = option.get("ask", 0) or 0

                dte = option.get("dte", None)
                if dte is None:
                    exp_str = option.get("expiration_date", "")
                    if exp_str:
                        try:
                            exp_date = datetime.date.fromisoformat(exp_str)
                            dte = (exp_date - today_date).days
                        except ValueError:
                            dte = 0
                    else:
                        dte = 0
                dte = int(dte or 0)

                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                elif ask > 0:
                    mid = ask
                else:
                    mid = 0

                greeks = option.get("greeks") or {}
                delta_raw = greeks.get("delta", None)
                delta = abs(float(delta_raw or 0)) if delta_raw is not None else 0.30

                iv = float(greeks.get("mid_iv", 0) or 0) or 0.30

                # Filter (unverändert)
                if oi < thr["options_oi_min"]: filter_stats["oi"] += 1; continue
                if not (thr["options_dte_min"] <= dte <= thr["options_dte_max"]): filter_stats["dte"] += 1; continue
                if not (thr["options_delta_min"] <= delta <= thr["options_delta_max"]): filter_stats["delta"] += 1; continue
                if mid == 0: filter_stats["mid"] += 1; continue

                if spot > 0:
                    intrinsic = max(spot - option.get("strike", 0), 0) if option.get("option_type") == "call" else max(option.get("strike", 0) - spot, 0)
                    if intrinsic > 0 and mid < intrinsic * 0.5: filter_stats["mid"] += 1; continue

                if bid > 0 and ask > 0:
                    spread_pct = (ask - bid) / mid
                    if spread_pct > thr["options_bid_ask_max_pct"]: filter_stats["spread"] += 1; continue

                filter_stats["passed"] += 1

                open_syms = [p["symbol"] for p in positions["open_positions"]]
                if option.get("symbol") in open_syms:
                    continue

                # ── NEU: Historische Optionsdaten holen ─────────────────────
                contract_symbol = option.get("symbol", "")
                if contract_symbol:
                    hist_data = fetcher.fetch_historical_option(contract_symbol, period="120d")
                    raw_data["historical_options"][contract_symbol] = hist_data

                # Quantitative Berechnungen (unverändert)
                r = raw_data.get("fred", {}).get("fed_funds_rate", 0.05)
                iv_adj = bs_calc.smile_adjusted_iv(iv, spot, option["strike"], smile)
                fv = bs_calc.fair_value(spot, option["strike"], r, dte/252, iv_adj, option.get("option_type", "call"))
                edge = (mid - fv) / mid * 100 if mid > 0 else 0

                ev, win_prob = mc_sim.simulate(
                    spot, option["strike"], r, dte/252, iv_adj, mid,
                    forecast.get("drift", 0), option.get("option_type", "call")
                )

                # ── NEU: ECHTES Backtesting statt Spot-Proxy ───────────────
                bt = backtester.find_similar_real({**option, **{
                    "symbol": contract_symbol,
                    "segment": seg,
                    "ticker": ticker,
                    "spot_price": spot,
                    "strike": option.get("strike"),
                    "expiry": option.get("expiration_date", ""),
                    "option_type": option.get("option_type", "call"),
                    "dte": dte,
                    "delta": delta,
                    "mid_price": mid,
                    "iv_pct": iv * 100,
                    "iv_rank": segment_scores[seg].get("iv_rank", 0),
                    "oi": oi,
                }})

                # Edge-Score (unverändert)
                ev_pct = ev / max(mid, 0.01) * 100
                ev_normalized = max(min(ev_pct, 100), -100)
                ev_component = (ev_normalized + 100) / 2

                es = (0.30 * ev_component +
                      0.25 * max(edge, 0) +
                      0.25 * bt.get("win_rate", 0.5) * 100 +
                      0.20 * forecast.get("confidence", 0.5) * 100)

                all_candidates.append({
                    "symbol": contract_symbol,
                    "segment": seg,
                    "ticker": ticker
