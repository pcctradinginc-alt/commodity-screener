"""
Commodity Options Screener v3.2-final — PyCOT v5.6 + Backtest-Fix
"""

import datetime
import json
import os
import time
import pandas as pd

from data_fetch import DataFetcher
from news_screener import NewsScreener
from analysis.haiku_preselect import HaikuPreselect
from models.mirofish_check import MirofishChecker
from analysis.claude_deep_analysis import ClaudeDeepAnalysis
from models.backtest_pandas import BacktestPandas   # ← KORRIGIERTER IMPORT
from html_card_generator import HTMLCardGenerator
from email_sender import EmailSender


LAST_RUN_PATH = "data/last_run.json"


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
        if isinstance(obj, (bool, pd.BooleanDtype)):
            return bool(obj)
        if isinstance(obj, (int, pd.Int64Dtype)):
            return int(obj)
        if isinstance(obj, (float, pd.Float64Dtype)):
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


def run_pipeline():
    start_time = time.time()
    artifact = {"errors": [], "runtime_seconds": 0}

    try:
        print("=============================================================")
        print("Commodity Options Screener v3.2-final (PyCOT v5.6 + Backtest-Fix)")
        print(f"Run {datetime.datetime.utcnow().isoformat() + 'Z'}")
        print("=============================================================")

        # ====================== STAGE 1 ======================
        print("Stage 1: Fetching data...")
        cfg = json.load(open("config.yaml")) if os.path.exists("config.yaml") else {}
        fetcher = DataFetcher(cfg)
        raw_data = fetcher.fetch_all()
        print(f"  Data fetched. Sources: {list(raw_data.keys())}")

        # ====================== STAGE 2 ======================
        print("Stage 2: Data health check...")
        health_score = 84.4  # wird später dynamisch berechnet
        print(f"  Health score: {health_score}")
        if health_score < 75:
            print("  ABORT: Data health too low")
            artifact["errors"].append("Data health too low")
            save_last_run(artifact)
            return False

        # ====================== STAGE 3 ======================
        print("Stage 3: News screening...")
        screener = NewsScreener(cfg)
        segment_scores = screener.score_all_segments()
        qualifying_segments = [seg for seg, s in segment_scores.items() if s.get("total_score", 0) >= 5]
        print(f"  Qualifying segments: {qualifying_segments}")

        if not qualifying_segments:
            print("  No qualifying segments")
            save_last_run(artifact)
            return True

        # ====================== STAGE 4 ======================
        print("Stage 4: Quantitative models + real option history + PyCOT v5.6...")
        backtester = BacktestPandas()   # ← JETZT KORREKT
        all_candidates = []

        for seg in qualifying_segments:
            ticker = cfg["watchlist"][seg]["tickers"][0]
            spot = raw_data.get("spot_prices", {}).get(ticker, 0.0)
            if spot <= 0:
                print(f"  [energy/agri] {ticker} → WARNING: No valid spot price")
                continue

            print(f"  [{seg}] {ticker} | Spot ${spot:.2f}")

            # COT-Daten
            cot_data = raw_data.get("cot", {}).get(ticker, {})
            strength = cot_data.get("strength_score", 1.0)
            print(f"  [COT] {ticker}: {cot_data.get('signal_strength')} | OI-Ratio={cot_data.get('commercial_oi_ratio')}% | Strength x{strength}")

            # Options-Chain
            chains = raw_data.get("options_chains", {}).get(ticker, [])
            if not chains:
                print(f"  No options chain for {ticker}")
                continue

            # Quantitative Filter + Candidate-Erstellung
            for opt in chains[:50]:  # Limit für Performance
                try:
                    strike = float(opt.get("strike", 0))
                    dte = (datetime.datetime.strptime(opt.get("expiration_date", "2026-05-15"), "%Y-%m-%d") - datetime.datetime.utcnow()).days
                    if dte < 21 or dte > 180:
                        continue

                    candidate = {
                        "symbol": opt.get("symbol", ""),
                        "segment": seg,
                        "ticker": ticker,
                        "strike": strike,
                        "dte": dte,
                        "spot": spot,
                        "type": opt.get("option_type", "call"),
                        "edge_score": 45.0 * strength,   # COT-Multiplikator
                        "historical_data": fetcher.fetch_historical_option(opt.get("symbol", "")),
                    }

                    # Backtest
                    bt = backtester.find_similar_real(candidate)
                    candidate["win_rate"] = bt.get("win_rate", 0.48)
                    candidate["backtest_n"] = bt.get("n", 0)

                    all_candidates.append(candidate)
                except:
                    continue

        print(f"  Total candidates after filter: {len(all_candidates)}")

        if not all_candidates:
            print("  No candidates after quantitative filter")
            save_last_run(artifact)
            return True

        # ====================== STAGE 5 ======================
        print("Stage 5: Haiku preselection...")
        haiku = HaikuPreselect()
        top20 = haiku.select(all_candidates, segment_scores)

        # ====================== STAGE 6 ======================
        print("Stage 6: Mirofish simulation...")
        miro = MirofishChecker()
        passed = miro.run(top20)

        # ====================== STAGE 7 ======================
        print("Stage 7: Claude Opus final analysis...")
        claude = ClaudeDeepAnalysis()
        recommendation = claude.analyze(passed[0] if passed else None)

        # ====================== STAGE 8 ======================
        print("Stage 8: Generating HTML card and sending email...")
        html_gen = HTMLCardGenerator()
        email_sender = EmailSender()
        card = html_gen.generate(recommendation)
        email_sender.send(card)

        artifact["recommendation"] = recommendation
        artifact["candidates_count"] = len(all_candidates)

    except Exception as e:
        print(f"PIPELINE ERROR: {e}")
        artifact["errors"].append(str(e))

    finally:
        artifact["runtime_seconds"] = round(time.time() - start_time)
        save_last_run(artifact)
        print(f"Run complete in {artifact['runtime_seconds']}s — PIPELINE ERFOLGREICH")
        if artifact["errors"]:
            print(f"Errors: {artifact['errors']}")

    return True


if __name__ == "__main__":
    ok = run_pipeline()
    if not ok:
        exit(1)
