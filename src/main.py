"""
Commodity Options Screener v3.4 — Prophet-Fix, EIA/FRED Macro-Multiplier, Spread-Adjustment
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
        # numpy scalars must come before Python builtins — np.bool_ is not a subclass
        # of Python bool since numpy 1.24, but IS a subclass of np.integer/np.floating
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, bool):
            return bool(obj)
        if isinstance(obj, int):
            return int(obj)
        if isinstance(obj, float):
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


def compute_eia_impact(raw_data: dict, seg: str) -> tuple:
    """
    Returns (impact_multiplier, eia_score) from enhanced EIA data.
    impact_multiplier: applied to cot_component (0.4–1.8)
    eia_score: mixed into MC drift (-1.0 to +1.0)
    """
    eia_data = raw_data.get("eia", {}).get(seg, {})
    if not eia_data:
        return 1.0, 0.0

    impact = 1.0
    eia_score = 0.0

    for series_id, series_info in eia_data.items():
        z     = series_info.get("z_score", 0)
        delta = series_info.get("delta", 0)
        sig   = series_info.get("signal", "NEUTRAL")

        # NG storage: tighter thresholds, larger impact (primary Aschenbrenner signal)
        if "NW2_EPG0_SWO_R48_BCF" in series_id:
            if z < -1.2:
                impact    = max(impact, 1.75)
                eia_score += 1.6
            elif z < -0.6:
                impact    = max(impact, 1.35)
                eia_score += 0.8
            elif z > 1.2:
                impact    = min(impact, 0.5)
                eia_score -= 1.2
            continue  # skip generic signal branch for this series

        if sig == "STRONG_BULLISH":
            impact    = max(impact, 1.8)
            eia_score += 1.0
        elif sig == "BULLISH":
            impact    = max(impact, 1.4)
            eia_score += 0.5
        elif sig == "STRONG_BEARISH":
            impact    = min(impact, 0.4)
            eia_score -= 1.0
        elif sig == "BEARISH":
            impact    = min(impact, 0.7)
            eia_score -= 0.5

    return round(impact, 2), round(max(-1.0, min(eia_score, 1.0)), 2)


def compute_aschenbrenner_bias(raw_data: dict, ticker: str,
                               iv_premium: float, call_skew_ratio: float,
                               cfg: dict) -> float:
    """
    Additive edge bonus (0–8 pts) for AI-infra tickers when ≥2 signals align.
    Signals are independent of each other and already in the main edge score —
    this is a small structural tilt, not a multiplier.
    """
    ab = cfg.get("aschenbrenner", {})
    if not ab.get("enabled", True):
        return 0.0
    if ticker not in ab.get("focus_tickers", []):
        return 0.0

    bias_max = float(ab.get("bias_max_points", 8.0))
    required = int(ab.get("required_signals", 2))
    signals  = 0

    # 1. COT strongly bullish
    cot = raw_data.get("cot", {}).get(ticker, {})
    if cot.get("z_score", 0) > 1.0 and cot.get("strength_score", 1.0) >= 1.5:
        signals += 1

    # 2. EIA strong inventory draw (energy signal, neutral for metals/nuclear)
    for series in raw_data.get("eia", {}).get("energy", {}).values():
        if series.get("z_score", 0) < -1.0 and series.get("delta", 0) < -3000:
            signals += 1
            break

    # 3. IV-Premium elevated (market pricing in supply-shock / infra-demand)
    if iv_premium > ab.get("iv_premium_threshold", 0.12):
        signals += 1

    # 4. Call-skew elevated (right-tail demand for physical commodity)
    if call_skew_ratio > 1.10:
        signals += 1

    if signals >= required:
        return round(bias_max * (signals / 4.0), 2)
    return 0.0


def compute_segment_skew(chains: list) -> float:
    """
    OTM call IV / OTM put IV ratio for a segment's options chain.
    >1.0 = market paying more for calls (right-tail / supply-shock demand).
    Returns 1.0 (neutral) when chain is empty or data insufficient.
    """
    call_ivs, put_ivs = [], []
    for opt in chains:
        iv    = float(opt.get("implied_volatility", 0) or 0)
        delta = abs(float(opt.get("delta", 0) or 0))
        otype = opt.get("option_type", "")
        if 0.15 <= delta <= 0.40 and iv > 0:
            if otype == "call":
                call_ivs.append(iv)
            else:
                put_ivs.append(iv)
    if call_ivs and put_ivs:
        return round((sum(call_ivs) / len(call_ivs)) / (sum(put_ivs) / len(put_ivs)), 3)
    return 1.0


def compute_macro_multiplier(raw_data: dict, seg: str, opt_type: str) -> float:
    """
    Returns a multiplier (0.70–1.35) based on EIA inventory shocks and FRED macro regime.
    Positive signals for the option direction push above 1.0, headwinds below.
    """
    multiplier = 1.0

    # EIA: inventory change (most relevant for energy, weaker signal for others)
    eia_seg = raw_data.get("eia", {}).get(seg, {})
    for series_data in eia_seg.values():
        pct = series_data.get("pct_change", 0)
        if opt_type == "call":
            if pct < -2.5:   multiplier *= 1.15   # inventory draw → bullish underlying
            elif pct > 3.0:  multiplier *= 0.85   # large build → bearish for calls
        else:
            if pct > 2.5:    multiplier *= 1.15   # large build → bearish underlying
            elif pct < -3.0: multiplier *= 0.85   # large draw → bearish for puts

    # FRED: dollar index and 10y rate
    fred = raw_data.get("fred", {})
    dxy  = fred.get("dollar_index", 0)
    r10y = fred.get("treasury_10y", 0)

    # DTWEXBGS broad trade-weighted index (normal range 110–130, not DXY 95–115)
    if dxy > 0:
        if dxy > 125:    multiplier *= 0.88   # very strong broad USD = commodity headwind
        elif dxy > 121:  multiplier *= 0.94
        elif dxy < 112:  multiplier *= 1.08   # weak broad USD = commodity tailwind

    if r10y > 4.5 and seg == "metals":
        multiplier *= 0.92   # high real rates = gold/silver headwind

    return round(max(0.70, min(multiplier, 1.35)), 3)


def compute_uranium_proxy_signal(yf_data: dict) -> tuple:
    """
    Sprott Physical Uranium Trust (SRUUF) momentum as uranium spot proxy.
    Returns (impact_multiplier, eia_score) with same semantics as compute_eia_impact().
    Signal: 5-day close vs 20-day MA normalized by 20-day std.
    """
    history = yf_data.get("SRUUF", [])
    closes = [r["Close"] for r in history if r.get("Close", 0) > 0]
    if len(closes) < 21:
        return 1.0, 0.0

    recent5  = np.mean(closes[-5:])
    ma20     = np.mean(closes[-20:])
    std20    = np.std(closes[-20:])
    if std20 == 0:
        return 1.0, 0.0

    z = (recent5 - ma20) / std20

    if z > 1.5:
        return 1.6, 0.8    # strong uranium spot rally → bullish URA/URNM
    elif z > 0.7:
        return 1.3, 0.4
    elif z < -1.5:
        return 0.6, -0.8   # uranium spot weakness → headwind
    elif z < -0.7:
        return 0.8, -0.4
    else:
        return 1.0, 0.0


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


            cot_data     = raw_data.get("cot", {}).get(ticker, {})
            cot_strength = cot_data.get("strength_score", 1.0)
            cot_z        = cot_data.get("z_score", 0.0)

            # EIA impact: multiplier for cot_component + additive score for MC drift
            eia_impact, eia_score = compute_eia_impact(raw_data, seg)

            # Nuclear: no EIA series → substitute with SRUUF uranium spot momentum
            if seg == "nuclear":
                u_impact, u_score = compute_uranium_proxy_signal(yf_data)
                eia_impact = u_impact
                eia_score  = u_score
                print(f"  [nuclear] SRUUF proxy → impact={u_impact:.2f}x score={u_score:+.2f}")

            # Prophet drift — mix EIA directional score into drift (80/20 blend)
            prophet_result = prophet.forecast(ticker)
            base_drift = prophet_result.get("drift", 0.0)
            drift      = base_drift * 0.8 + eia_score * 0.05   # EIA adds up to ±0.05 drift
            prop_dir   = prophet_result.get("direction", "neutral")

            # Call-Skew: OTM call IV / OTM put IV (right-tail demand indicator)
            chains = raw_data.get("options_chains", {}).get(ticker, [])
            call_skew_ratio = compute_segment_skew(chains)

            print(f"  [{seg}] {ticker} | Spot ${spot:.2f} | HV={hv:.1%} | "
                  f"COT={cot_data.get('signal_strength')} z={cot_z:.2f} | "
                  f"EIA={eia_impact:.2f}x | Skew={call_skew_ratio:.3f} | "
                  f"Prophet={prop_dir} drift={drift:+.4f}")

            accepted = 0

            # Pre-filter: only options in the delta zone before applying the cap.
            # Tradier chains are sorted by strike (ascending), so a naive [:80] slice
            # on a 942-contract chain lands entirely in deep-OTM/deep-ITM territory.
            delta_lo = delta_min - 0.05  # slight margin to catch greeks rounding
            delta_hi = delta_max + 0.05
            relevant_chains = [
                opt for opt in chains
                if delta_lo <= abs(float(opt.get("delta", 0) or 0)) <= delta_hi
            ]
            if not relevant_chains:
                relevant_chains = chains  # fallback: no pre-filter if no greeks available

            for opt in relevant_chains[:MAX_CANDIDATES_PER_SEGMENT]:
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
                    spread_pct = (ask - bid) / ask if bid > 0 and ask > 0 else 0.05
                    bt = backtester.find_similar_real({
                        "symbol": symbol, "spot": spot, "strike": strike,
                        "dte": dte, "option_type": opt_type, "mid_price": mid_price,
                        "spread_pct": spread_pct,
                        "underlying_history": underlying_history,
                    })

                    # --- Combined edge score ---
                    cot_component  = (cot_strength * 20 + cot_z * 8) * eia_impact
                    bs_component   = max(0.0, bs_edge * 100)
                    mc_component   = max(0.0, mc_ev / 5.0)
                    hist_component = bt.get("win_rate", 0.48) * 20

                    # IV-Premium: market paying above HV = expects big move (good for long)
                    iv_premium     = max(0.0, market_iv / hv - 1.0) if hv > 0 else 0.0
                    iv_prem_pts    = min(iv_premium * 40, 20.0)   # cap at 20 pts

                    # Call-skew contribution: >1.0 = right-tail demand
                    skew_pts       = max(0.0, (call_skew_ratio - 1.0) * 30)

                    vol_regime_component = 0.6 * iv_prem_pts + 0.4 * skew_pts

                    raw_edge = (
                        0.30 * cot_component +
                        0.30 * bs_component +
                        0.20 * mc_component +
                        0.08 * hist_component +
                        0.12 * vol_regime_component
                    )
                    macro_mult = compute_macro_multiplier(raw_data, seg, opt_type)
                    edge_score = round(raw_edge * macro_mult, 2)

                    # Soft infra-demand bias: only when COT + EIA + Skew all simultaneously strong
                    if cot_z > 1.5 and eia_impact >= 1.4 and call_skew_ratio > 1.15:
                        edge_score = round(edge_score * 1.12, 2)

                    # Aschenbrenner structural tilt: additive +0–8 pts for AI-infra tickers
                    ab_bias = compute_aschenbrenner_bias(
                        raw_data, ticker, iv_premium, call_skew_ratio, cfg
                    )
                    edge_score = round(edge_score + ab_bias, 2)

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
                        "cot_strength":      cot_strength,
                        "cot_z":             cot_z,
                        "prophet_drift":     drift,
                        "prophet_direction": prop_dir,
                        "macro_multiplier":  macro_mult,
                        "iv_premium":           round(iv_premium, 3),
                        "call_skew_ratio":      call_skew_ratio,
                        "aschenbrenner_bias":   ab_bias,
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
