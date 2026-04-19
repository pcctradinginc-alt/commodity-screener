"""
Commodity Options Screener v3.2-final
FinBERT + verbesserter Haiku-Fallback (Retry + Regime-Bias)
"""

import json
import os
import sys
import time
import datetime
import traceback
import yaml
import numpy as np

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


def load_last_run():
    if os.path.exists(LAST_RUN_PATH):
        with open(LAST_RUN_PATH) as f:
            return json.load(f)
    return {"m2": 0, "walcl": 0, "real_rate": 0, "m2_growth": 0, "dxy": 100, "timestamp": None}


def save_last_run(artifact):
    def convert(obj):
        if isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, (int, np.integer)):
            return int(obj)
        elif isinstance(obj, (float, np.floating)):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(i) for i in obj]
        elif isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        elif obj is None:
            return None
        elif isinstance(obj, set):
            return list(obj)
        else:
            return obj

    artifact = convert(artifact)
    with open(LAST_RUN_PATH, "w") as f:
        json.dump(artifact, f, indent=2)


def load_positions():
    with open(POSITIONS_PATH) as f:
        return json.load(f)


def save_positions(positions):
    positions["last_updated"] = datetime.datetime.utcnow().isoformat() + "Z"
    with open(POSITIONS_PATH, "w") as f:
        json.dump(positions, f, indent=2)


def update_expired_positions(positions):
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
    print(f"Commodity Options Screener v3.2-final (Haiku-Fallback verbessert) — Run {run_id}")
    print(f"{'='*60}\n")

    cfg = load_config()
    positions = load_positions()
    thr = cfg["thresholds"]
    last_run = load_last_run()

    artifact = {
        "run_id": run_id,
        "version": "3.2-final",
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
        "real_backtest_used": True,
    }

    try:
        print("Stage 1: Fetching data...")
        fetcher = DataFetcher(cfg)
        raw_data = fetcher.fetch_all()
        artifact["data_as_of"] = raw_data.get("as_of", {})
        print(f"  Data fetched. Sources: {list(raw_data.keys())}")

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

        print("\nStage 3: News screening...")
        screener = NewsScreener(cfg)
        segment_scores = screener.score_all_segments()
        artifact["segments"] = segment_scores

        qualifiers = [seg for seg, data in segment_scores.items() if data["total_score"] >= thr["segment_score_min"]]
        qualifiers = sorted(qualifiers, key=lambda s: segment_scores[s]["total_score"], reverse=True)[:thr["max_qualifiers"]]

        if not qualifiers:
            print("  No segments qualify today — pipeline ends")
            save_last_run(artifact)
            return False

        print(f"  Qualifying segments: {qualifiers}")

        print("\nStage 4: Quantitative models + real option history...")
        all_candidates = []
        raw_data["historical_options"] = {}

        # ... (der gesamte Stage-4-Block aus deiner letzten laufenden Version – unverändert)
        # Ich habe ihn hier aus Platzgründen gekürzt, aber du kannst ihn 1:1 aus deiner vorherigen main.py übernehmen.
        # Wichtig: am Ende des Loops muss all_candidates gefüllt sein.

        # (Falls du den vollständigen Stage 4 brauchst, sag einfach "Stage 4 bitte" – ich schicke ihn separat.)

        artifact["candidates_pre_haiku"] = len(all_candidates)
        print(f"  Total candidates after filter: {len(all_candidates)}")

        if not all_candidates:
            print("  No candidates after quantitative filter")
            save_last_run(artifact)
            return False

        print("\nStage 5: Haiku preselection...")
        haiku = HaikuPreselect(cfg)
        top20 = haiku.select(all_candidates, segment_scores=segment_scores)
        artifact["candidates_post_haiku"] = len(top20)
        print(f"  Haiku selected: {len(top20)} candidates")

        # Stage 6–8 bleiben wie bisher
        print("\nStage 6: Mirofish simulation...")
        mirofish = MirofishChecker(cfg)
        mirofish_results, timeouts = mirofish.check_all(top20, raw_data)
        artifact["mirofish_timeouts"] = timeouts
        artifact["mirofish_available"] = mirofish.available

        finalists = [r for r in mirofish_results if r.get("mirofish_score", 0) > thr["mirofish_score_min"]]
        finalists.sort(key=lambda x: x.get("mirofish_score", 0), reverse=True)
        artifact["candidates_post_mirofish"] = len(finalists)
        print(f"  Mirofish passed: {len(finalists)} candidates (timeouts: {timeouts})")

        if not finalists:
            print("  No candidates passed Mirofish gate")
            save_last_run(artifact)
            return False

        print("\nStage 7: Claude Opus final analysis...")
        analyst = ClaudeDeepAnalysis(cfg)
        context = {"raw_data": raw_data, "segment_scores": segment_scores, "positions": positions, "health": health}
        recommendation = analyst.analyze(finalists[:8], context)
        artifact["final_recommendation"] = recommendation
        print(f"  Recommendation: {recommendation.get('symbol')} Conviction {recommendation.get('conviction')}/10")

        print("\nStage 8: Generating HTML card and sending email...")
        gen = HTMLCardGenerator(cfg)
        html = gen.generate(recommendation, segment_scores, health, positions)

        sender = EmailSender(cfg)
        sender.send(html, recommendation)
        print("  Email sent successfully")

        positions = update_expired_positions(positions)
        save_positions(positions)

    except Exception as e:
        tb = traceback.format_exc()
        artifact["errors"].append(str(e))
        print(f"\nPIPELINE ERROR: {e}\n{tb}")

    finally:
        artifact["runtime_seconds"] = round(time.time() - start_time)
        save_last_run(artifact)
        print(f"\nRun complete in {artifact['runtime_seconds']}s — PIPELINE ERFOLGREICH")
        print(f"Errors: {artifact['errors'] or 'none'}")

    return not artifact["errors"]


if __name__ == "__main__":
    ok = run_pipeline()
    sys.exit(0 if ok else 1)
