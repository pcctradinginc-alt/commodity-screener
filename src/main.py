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

    artifact = { ... }   # (wie bisher – unverändert)

    try:
        # Stage 1–4 bleiben exakt wie in deiner letzten Version
        # ... (kopiere sie aus deiner aktuellen main.py)

        print("\nStage 5: Haiku preselection...")
        haiku = HaikuPreselect(cfg)

        # Intelligenter Retry + Regime-Bias
        top20 = haiku.select(
            all_candidates,
            segment_scores=segment_scores,          # für Regime-Bias
            global_regime_multiplier=1.0
        )

        artifact["candidates_post_haiku"] = len(top20)
        print(f"  Haiku selected: {len(top20)} candidates")

        # ... Stage 6–8 bleiben unverändert

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
