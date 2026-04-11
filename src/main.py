"""
Commodity Options Screener v3.1
Pipeline Orchestrator
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
from models.backtest_pandas import BacktestEngine
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
    print(f"Commodity Options Screener v3.1 — Run {run_id}")
    print(f"{'='*60}\n")

    cfg = load_config()
    positions = load_positions()
    thr = cfg["thresholds"]

    artifact = {
        "run_id": run_id,
        "version": "3.1",
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

        # ── Stage 4: Quantitative Models ────────────────────────────
        print("\nStage 4: Quantitative models...")
        all_candidates = []

        for seg in qualifiers:
            ticker = cfg["watchlist"][seg]["tickers"][0]
            smile = cfg["watchlist"][seg].get("smile_factor", 0.15)
            print(f"  [{seg}] {ticker}")

            prophet = ProphetForecaster(cfg, raw_data)
            forecast = prophet.forecast(seg)

            bs_calc = BlackScholesCalculator(cfg)
            mc_sim = MonteCarloSimulator(cfg)
            backtester = BacktestEngine(cfg, raw_data)

            chain = raw_data.get("options_chains", {}).get(ticker, [])
            for option in chain:
                oi = option.get("open_interest", 0) or 0
                volume = option.get("volume", 0) or 0
                bid = option.get("bid", 0) or 0
                ask = option.get("ask", 0) or 0
                mid = (bid + ask) / 2 if bid and ask else 0
                dte = option.get("dte", 0) or 0
                delta = abs(float((option.get("greeks") or {}).get("delta", 0) or 0))
                iv = float((option.get("greeks") or {}).get("mid_iv", 0) or 0)

                if oi < thr["options_oi_min"]: continue
                if volume < thr["options_volume_min"]: continue
                if not (thr["options_dte_min"] <= dte <= thr["options_dte_max"]): continue
                if not (thr["options_delta_min"] <= delta <= thr["options_delta_max"]): continue
                if mid == 0: continue
                spread_pct = (ask - bid) / mid if mid > 0 else 1
                if spread_pct > thr["options_bid_ask_max_pct"]: continue

                open_syms = [p["symbol"] for p in positions["open_positions"]]
                if option.get("symbol") in open_syms: continue

                spot = raw_data.get("quotes", {}).get(ticker, {}).get("c", 0)
                r = raw_data.get("fred", {}).get("fed_funds_rate", 0.05)
                iv_adj = bs_calc.smile_adjusted_iv(iv, spot, option["strike"], smile)
                fv = bs_calc.fair_value(spot, option["strike"], r, dte/252, iv_adj,
                                        option.get("option_type", "call"))
                edge = (mid - fv) / mid * 100 if mid > 0 else 0

                ev, win_prob = mc_sim.simulate(spot, option["strike"], r,
                                               dte/252, iv_adj, mid,
                                               forecast.get("drift", 0))
                bt = backtester.find_similar(seg, iv*100, dte)

                es = (0.30 * min(max(ev/mid*100, 0), 100) +
                      0.25 * max(edge, 0) +
                      0.25 * bt.get("win_rate", 0.5) * 100 +
                      0.20 * forecast.get("confidence", 0.5) * 100)

                all_candidates.append({
                    "symbol":           option.get("symbol", ""),
                    "segment":          seg,
                    "ticker":           ticker,
                    "strike":           option.get("strike"),
                    "expiry":           option.get("expiration_date", ""),
                    "option_type":      option.get("option_type", "call"),
                    "dte":              dte,
                    "delta":            round(delta, 3),
                    "mid_price":        round(mid, 2),
                    "iv_pct":           round(iv * 100, 1),
                    "iv_rank":          segment_scores[seg].get("iv_rank", 0),
                    "oi":               oi,
                    "volume":           volume,
                    "fair_value_bs":    round(fv, 2),
                    "edge_score":       round(es, 1),
                    "mc_ev":            round(ev, 2),
                    "mc_win_prob":      round(win_prob, 3),
                    "hist_win_rate":    round(bt.get("win_rate", 0), 3),
                    "hist_sharpe":      round(bt.get("sharpe", 0), 2),
                    "hist_sample_size": bt.get("sample_size", 0),
                    "prophet_drift":    round(forecast.get("drift", 0), 4),
                    "prophet_confidence": round(forecast.get("confidence", 0), 3),
                    "mirofish_score":   0,
                    "mirofish_confidence": "none",
                })

        artifact["candidates_pre_haiku"] = len(all_candidates)
        print(f"  Total candidates after filter: {len(all_candidates)}")

        if not all_candidates:
            print("  No candidates after quantitative filter")
            save_last_run(artifact)
            return False

        # ── Stage 5: Haiku Preselection ──────────────────────────────
        print("\nStage 5: Haiku preselection...")
        haiku = HaikuPreselect(cfg)
        top20 = haiku.select(all_candidates)
        artifact["candidates_post_haiku"] = len(top20)
        print(f"  Haiku selected: {len(top20)} candidates")

        # ── Stage 6: Mirofish ────────────────────────────────────────
        print("\nStage 6: Mirofish simulation...")
        mirofish = MirofishChecker(cfg)
        mirofish_results, timeouts = mirofish.check_all(top20, raw_data)
        artifact["mirofish_timeouts"] = timeouts
        artifact["mirofish_available"] = mirofish.available

        finalists = [
            r for r in mirofish_results
            if r.get("mirofish_score", 0) > thr["mirofish_score_min"]
        ]
        finalists.sort(key=lambda x: x.get("mirofish_score", 0), reverse=True)
        artifact["candidates_post_mirofish"] = len(finalists)
        print(f"  Mirofish passed: {len(finalists)} candidates (timeouts: {timeouts})")

        if not finalists:
            print("  No candidates passed Mirofish gate")
            save_last_run(artifact)
            return False

        # ── Stage 7: Claude Opus Final Analysis ─────────────────────
        print("\nStage 7: Claude Opus final analysis...")
        analyst = ClaudeDeepAnalysis(cfg)
        context = {
            "raw_data": raw_data,
            "segment_scores": segment_scores,
            "positions": positions,
            "health": health,
        }
        recommendation = analyst.analyze(finalists[:8], context)
        artifact["final_recommendation"] = recommendation
        print(f"  Recommendation: {recommendation.get('symbol')} "
              f"Conviction {recommendation.get('conviction')}/10")

        # ── Stage 8: HTML Card + Email ───────────────────────────────
        print("\nStage 8: Generating HTML card and sending email...")
        gen = HTMLCardGenerator(cfg)
        html = gen.generate(recommendation, segment_scores, health, positions)

        sender = EmailSender(cfg)
        sender.send(html, recommendation)
        print("  Email sent successfully")

        # ── Update positions ─────────────────────────────────────────
        positions = update_expired_positions(positions, os.environ.get("TRADIER_KEY", ""))
        save_positions(positions)

    except Exception as e:
        tb = traceback.format_exc()
        artifact["errors"].append(str(e))
        print(f"\nPIPELINE ERROR: {e}\n{tb}")

    finally:
        artifact["runtime_seconds"] = round(time.time() - start_time)
        save_last_run(artifact)
        print(f"\nRun complete in {artifact['runtime_seconds']}s")
        print(f"Errors: {artifact['errors'] or 'none'}")

    return not artifact["errors"]


if __name__ == "__main__":
    ok = run_pipeline()
    sys.exit(0 if ok else 1)
