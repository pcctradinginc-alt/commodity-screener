"""
Mirofish Simulation — Pfad-basiertes Gate
JETZT MIT MERTON JUMP-DIFFUSION + REGIME-SWITCHING
Bessere Abbildung von Commodity-Jumps (EIA, COT, OPEC etc.)
"""

import logging
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

log = logging.getLogger(__name__)

N_PATHS   = 100_000
THRESHOLD = 0.25    # 25% profitable Pfade bei Expiry

SECTOR_VOL_MULT = {
    "Energy":            1.25,
    "Basic Materials":   1.15,
    "Technology":        1.10,
    "Financial":         1.05,
    "Consumer Cyclical": 1.00,
    "default":           1.00,
}

NARRATIVE_DECAY = {
    "short":  0.018,
    "medium": 0.009,
    "long":   0.004,
}

# Neue Regime-Parameter
JUMP_PROB_BASE = 0.025          # normale Tage
JUMP_PROB_RELEASE = 0.12        # EIA / COT Release-Tage
JUMP_SIZE_MEAN = 0.0
JUMP_SIZE_STD = 0.045           # ±4.5% typische Commodity-Jumps


class MirofishChecker:
    def __init__(self, cfg):
        self.cfg      = cfg
        self.timeout  = cfg["thresholds"].get("mirofish_timeout_seconds", 60)
        self.workers  = cfg["thresholds"].get("mirofish_parallel_workers", 4)
        self.available = True
        print("  Mirofish: Python Jump-Diffusion Engine geladen (Regime-Switching aktiv)")

    def _get_market_params(self, ticker):
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="35d")
            price  = float(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0)
            sector = info.get("sector", "default")
            if len(hist) >= 10:
                returns = hist["Close"].pct_change().dropna()
                sigma   = float(np.std(returns))
            else:
                sigma = 0.02
            return sigma, price, sector
        except Exception:
            return 0.02, 0.0, "default"

    def _get_market_params_sector_only(self, ticker):
        try:
            info   = yf.Ticker(ticker).info
            sector = info.get("sector", "default")
            return 0.0, 0.0, sector
        except Exception:
            return 0.0, 0.0, "default"

    def _decay_bucket(self, dte):
        if dte < 30:   return "short"
        if dte < 90:   return "medium"
        return "long"

    def _is_release_regime(self, dte):
        """Einfache Regime-Erkennung: höhere Jump-Wahrscheinlichkeit an Release-Tagen"""
        # EIA meist Mittwoch, COT Freitag → je nach Restlaufzeit approximieren
        weekday_in_dte = (datetime.date.today().weekday() + dte) % 7
        is_eia_day = weekday_in_dte in [2]      # Mittwoch
        is_cot_day = weekday_in_dte in [4]      # Freitag
        return is_eia_day or is_cot_day

    def _simulate_one(self, candidate):
        ticker    = candidate.get("ticker", "")
        dte       = candidate.get("dte", 45)
        opt_type  = candidate.get("option_type", "call").upper()
        strike    = float(candidate.get("strike", 0))
        premium   = float(candidate.get("mid_price", 0))
        news_raw  = candidate.get("news_raw_score", 5)
        cot_net   = candidate.get("cot_net", 0)

        # Tradier IV (annualisiert → daily)
        iv_annual = candidate.get("iv_pct", 30) / 100
        sigma_daily = iv_annual / np.sqrt(252)

        current_price = float(candidate.get("spot_price", 0))
        if current_price <= 0:
            _, current_price, sector = self._get_market_params(ticker)
        else:
            _, _, sector = self._get_market_params_sector_only(ticker)

        if current_price <= 0 or strike <= 0 or premium <= 0:
            return {**candidate, "mirofish_score": 0, "mirofish_confidence": "none", "agent_consensus": "no_data"}

        vol_mult  = SECTOR_VOL_MULT.get(sector, 1.0)
        sigma_adj = sigma_daily * vol_mult

        # Drift (News + COT)
        base_alpha  = (news_raw / 83.0) * 0.008
        cot_alpha   = np.sign(cot_net) * min(abs(cot_net) / 1_000_000, 0.003)
        direction   = "BULLISH" if opt_type == "CALL" else "BEARISH"
        total_alpha = base_alpha + cot_alpha
        if direction == "BEARISH":
            total_alpha = -total_alpha

        decay_rate = NARRATIVE_DECAY[self._decay_bucket(dte)]
        n_days = min(dte, 180)

        # ── Jump-Diffusion Regime ─────────────────────────────────────
        is_release = self._is_release_regime(dte)
        jump_prob = JUMP_PROB_RELEASE if is_release else JUMP_PROB_BASE

        rng = np.random.default_rng(seed=42)
        alphas = np.array([total_alpha * np.exp(-decay_rate * d) for d in range(n_days)])

        # Vektorisiertes Jump-Diffusion
        Z = rng.standard_normal((N_PATHS, n_days))                    # Brownian Motion
        jumps = rng.poisson(jump_prob, size=(N_PATHS, n_days))        # Anzahl Jumps pro Tag
        jump_sizes = rng.normal(JUMP_SIZE_MEAN, JUMP_SIZE_STD, size=(N_PATHS, n_days))
        jump_component = jumps * jump_sizes

        daily_returns = alphas[np.newaxis, :] + sigma_adj * Z + jump_component
        log_returns   = np.log1p(daily_returns)
        prices        = current_price * np.exp(np.cumsum(log_returns, axis=1))

        final_prices = prices[:, -1]

        # Payoff
        if direction == "BULLISH":
            payoffs = np.maximum(final_prices - strike, 0)
        else:
            payoffs = np.maximum(strike - final_prices, 0)

        profitable = payoffs > premium
        ev_per_contract = float((payoffs - premium).mean() * 100)

        profit_rate = float(profitable.mean())
        mirofish_score = round(profit_rate * 100)

        if profit_rate >= 0.45:
            confidence = "high"
        elif profit_rate >= 0.30:
            confidence = "medium"
        elif profit_rate >= 0.15:
            confidence = "low"
        else:
            confidence = "none"

        consensus = "bullish" if direction == "BULLISH" else "bearish"

        regime_str = "RELEASE-DAY" if is_release else "normal"
        print(f"  [{ticker} {opt_type} {strike:.1f} @${premium:.2f}] "
              f"profit_rate={profit_rate:.1%} ev=${ev_per_contract:.0f} "
              f"score={mirofish_score} jumps={jump_prob:.1%} ({regime_str}) "
              f"({'PASS' if profit_rate >= THRESHOLD else 'FAIL'})")

        return {
            **candidate,
            "mirofish_score": mirofish_score,
            "mirofish_confidence": confidence,
            "agent_consensus": consensus,
            "mirofish_ev": round(ev_per_contract, 2),
            "simulation": {
                "profit_rate": round(profit_rate, 4),
                "ev_contract": round(ev_per_contract, 2),
                "n_paths": N_PATHS,
                "n_days": n_days,
                "strike": round(strike, 2),
                "premium": round(premium, 2),
                "current_price": round(current_price, 2),
                "sigma_adj": round(sigma_adj, 4),
                "sector": sector,
                "direction": direction,
                "jump_prob": round(jump_prob, 4),
                "regime": regime_str,
            },
        }

    def _run_one_safe(self, candidate):
        sym = candidate.get("symbol", "?")
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(self._simulate_one, candidate)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeout:
                print(f"    Mirofish timeout: {sym}")
                return {**candidate, "mirofish_score": 0, "mirofish_confidence": "none", "agent_consensus": "timeout"}
            except Exception as e:
                print(f"    Mirofish error {sym}: {e}")
                return {**candidate, "mirofish_score": 0, "mirofish_confidence": "none", "agent_consensus": "error"}

    def check_all(self, candidates, raw_data):
        if not candidates:
            return [], 0

        cot_map = {seg: cot.get("net_commercial", 0) for seg, cot in raw_data.get("cot", {}).items()}
        news_map = {seg: sd.get("news_raw", 5) for seg, sd in raw_data.get("segment_scores", {}).items()}

        enriched = []
        for c in candidates:
            seg = c.get("segment", "")
            enriched.append({
                **c,
                "cot_net": cot_map.get(seg, 0),
                "news_raw_score": news_map.get(seg, 5),
            })

        print(f"  Mirofish Jump-Diffusion: {len(enriched)} Kandidaten "
              f"({self.workers} parallel, {self.timeout}s timeout)")

        results = []
        timeouts = 0

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._run_one_safe, c): c for c in enriched}
            for future in futures:
                result = future.result()
                results.append(result)
                if result.get("agent_consensus") in ("timeout", "error"):
                    timeouts += 1

        results.sort(key=lambda x: x.get("mirofish_score", 0), reverse=True)
        thr = self.cfg["thresholds"]["mirofish_score_min"]
        passed = sum(1 for r in results if r.get("mirofish_score", 0) > thr)
        print(f"  Mirofish: {passed} passed gate (>{thr}), {timeouts} timeouts")

        return results, timeouts
