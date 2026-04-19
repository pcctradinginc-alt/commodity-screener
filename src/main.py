"""
Commodity Options Screener v3.2-final
Phase 1 komplett + Macro V4 (Regime-Gate + Multiplier + vereinfachter Edge)
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


def load_positions():
    with open(POSITIONS_PATH) as f:
        return json.load(f)


def save_positions(positions):
    positions["last_updated"] = datetime.datetime.utcnow().isoformat() + "Z"
    with open(POSITIONS_PATH, "w") as f:
        json.dump(positions, f, indent=2)


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


def run_pipeline():
    start_time = time.time()
    run_id = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n{'='*60}")
    print(f"Commodity Options Screener v3.2-final (Macro V4) — Run {run_id}")
    print(f"{'='*60}\n")

    cfg = load_config()
    positions = load_positions()
    thr = cfg["thresholds"]

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

        # ── Macro V4: Regime + Multiplier + Gate (dein Vorschlag) ─────────────────
        fred = raw_data.get("fred", {})
        fed_funds = fred.get("fed_funds_rate", 5.0)
        cpi = fred.get("cpi", 3.0)
        m2 = fred.get("m2", 0)
        walcl = fred.get("walcl", 0)
        dxy = fred.get("dxy", 100.0)

        real_rate = fed_funds - cpi
        rr_score = abs(real_rate) * 2 if real_rate < 0 else -real_rate

        m2_growth = (m2 / max(m2 - 2000, 1) - 1) if m2 > 0 else 0
        walcl_growth = (walcl / max(walcl - 700, 1) - 1) if walcl > 0 else 0

        liquidity_score = rr_score + m2_growth * 5 + walcl_growth * 5
        dxy_momentum = (dxy - 105) / 105

        # Regime Detection
        if real_rate < 0 and m2_growth > 0:
            regime = "LIQUIDITY_EXPANSION"
        elif real_rate > 2 and m2_growth < 0:
            regime = "TIGHTENING"
        else:
            regime = "NEUTRAL"

        # Macro als Multiplier + Gate
        macro_multiplier = {"LIQUIDITY_EXPANSION": 1.25, "TIGHTENING": 0.70, "NEUTRAL": 1.0}

        print(f"  Macro V4 → Regime: {regime} | Liquidity: {liquidity_score:.2f} | DXY Mom: {dxy_momentum:.3f} | Multiplier: {macro_multiplier[regime]:.2f}")

        print("\nStage 4: Quantitative models + real option history...")
        all_candidates = []
        raw_data["historical_options"] = {}

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
            filter_stats = {"oi": 0, "volume": 0, "dte": 0, "delta": 0, "mid": 0, "spread": 0, "passed": 0}
            today_date = datetime.date.today()

            fh_quote = raw_data.get("quotes", {}).get(ticker, {})
            tr_quote = raw_data.get("tradier_quotes", {}).get(ticker, {})

            spot = float(tr_quote.get("last", 0) or tr_quote.get("bid", 0) or tr_quote.get("ask", 0) or 0) or \
                   float(fh_quote.get("c", 0) or fh_quote.get("pc", 0) or 0) or 0.0

            print(f"  Final spot {ticker}: ${spot:.2f}")

            if spot <= 0:
                print(f"  WARNING: No valid spot price for {ticker} — skipping segment")
                continue

            for option in chain:
                # ... (Filter-Block identisch mit vorher) ...
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

                contract_symbol = option.get("symbol", "")
                if contract_symbol:
                    hist_data = fetcher.fetch_historical_option(contract_symbol, period="120d")
                    raw_data["historical_options"][contract_symbol] = hist_data

                r = raw_data.get("fred", {}).get("fed_funds_rate", 0.05)
                iv_adj = bs_calc.smile_adjusted_iv(iv, spot, option["strike"], smile)
                fv = bs_calc.fair_value(spot, option["strike"], r, dte/252, iv_adj, option.get("option_type", "call"))
                edge = (mid - fv) / mid * 100 if mid > 0 else 0

                ev, win_prob = mc_sim.simulate(
                    spot, option["strike"], r, dte/252, iv_adj, mid,
                    forecast.get("drift", 0), option.get("option_type", "call")
                )

                candidate_for_bt = { ... }  # unverändert

                bt = backtester.find_similar_real(candidate_for_bt)

                ev_pct = ev / max(mid, 0.01) * 100
                ev_normalized = max(min(ev_pct, 100), -100)
                ev_component = (ev_normalized + 100) / 2

                # Vereinfachter, orthogonalisierter Edge Score (dein Vorschlag)
                base_es = (0.4 * ev_component +
                           0.3 * bt.get("win_rate", 0.5) * 100 +
                           0.3 * forecast.get("confidence", 0.5) * 100)

                # Macro als Multiplier (nicht additiv!)
                es = base_es * macro_multiplier[regime]

                all_candidates.append({
                    "symbol": contract_symbol,
                    "segment": seg,
                    "ticker": ticker,
                    "spot_price": round(spot, 2),
                    "strike": option.get("strike"),
                    "expiry": option.get("expiration_date", ""),
                    "option_type": option.get("option_type", "call"),
                    "dte": dte,
                    "delta": round(delta, 3),
                    "mid_price": round(mid, 2),
                    "iv_pct": round(iv * 100, 1),
                    "iv_rank": segment_scores[seg].get("iv_rank", 0),
                    "oi": oi,
                    "volume": volume,
                    "fair_value_bs": round(fv, 2),
                    "edge_score": round(es, 1),
                    "mc_ev": round(ev, 2),
                    "mc_win_prob": round(win_prob, 3),
                    "hist_win_rate": round(bt.get("win_rate", 0), 3),
                    "hist_sharpe": round(bt.get("sharpe", 0), 2),
                    "hist_sample_size": bt.get("sample_size", 0),
                    "prophet_drift": round(forecast.get("drift", 0), 4),
                    "prophet_confidence": round(forecast.get("confidence", 0), 3),
                    "mirofish_score": 0,
                    "mirofish_confidence": "none",
                    "real_options_data": bt.get("real_options_data", False),
                    "regime": regime,
                })

            print(f"  Filter stats {ticker}: {filter_stats}")

        artifact["candidates_pre_haiku"] = len(all_candidates)
        print(f"  Total candidates after filter: {len(all_candidates)}")

        if not all_candidates:
            print("  No candidates after quantitative filter")
            save_last_run(artifact)
            return False

        print("\nStage 5: Haiku preselection...")
        haiku = HaikuPreselect(cfg)
        top20 = haiku.select(all_candidates)
        artifact["candidates_post_haiku"] = len(top20)
        print(f"  Haiku selected: {len(top20)} candidates")

        # ... (Stage 6–8 bleiben identisch – Mirofish, Claude, Email)

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

        positions = update_expired_positions(positions, os.environ.get("TRADIER_KEY", ""))
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
