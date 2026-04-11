"""
Mirofish Simulation — Pfad-basiertes Gate
Adapted from MirofishSimulation pattern:
  10.000 Monte-Carlo-Pfade über DTE Tage
  Adoption-Drift aus News-Score + COT-Signal
  Narrative-Decay: Nachrichteneffekt nimmt täglich ab
  Gate: > 65% der Pfade müssen Strike erreichen
"""

import logging
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

log = logging.getLogger(__name__)

N_PATHS   = 100_000
THRESHOLD = 0.65    # 65% der Pfade müssen Strike erreichen

SECTOR_VOL_MULT = {
    "Energy":            1.2,
    "Basic Materials":   1.1,
    "Technology":        1.3,
    "Financial":         1.1,
    "Consumer Cyclical": 1.0,
    "default":           1.0,
}

NARRATIVE_DECAY = {
    "short":  0.015,   # < 30 DTE: schnelle Erosion
    "medium": 0.008,   # 30-90 DTE
    "long":   0.004,   # > 90 DTE: langsame Erosion
}


class MirofishChecker:
    def __init__(self, cfg):
        self.cfg      = cfg
        self.timeout  = cfg["thresholds"].get("mirofish_timeout_seconds", 60)
        self.workers  = cfg["thresholds"].get("mirofish_parallel_workers", 4)
        self.available = True   # immer verfügbar — reines Python
        print("  Mirofish: Python Monte-Carlo engine geladen")

    def _get_market_params(self, ticker):
        """Holt sigma, current_price, sector von yfinance."""
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="35d")
            price  = float(info.get("currentPrice") or
                           info.get("regularMarketPrice") or
                           info.get("previousClose") or 0)
            sector = info.get("sector", "default")
            if len(hist) >= 10:
                returns = hist["Close"].pct_change().dropna()
                sigma   = float(np.std(returns))
            else:
                sigma = 0.02
            return sigma, price, sector
        except Exception as e:
            log.debug(f"  yfinance {ticker}: {e}")
            return 0.02, 0.0, "default"

    def _decay_bucket(self, dte):
        if dte < 30:   return "short"
        if dte < 90:   return "medium"
        return "long"

    def _simulate_one(self, candidate):
        """
        Monte-Carlo Pfad-Simulation für einen Options-Kandidaten.
        Gibt candidate + mirofish_score + simulation-Details zurück.
        """
        ticker    = candidate.get("ticker", "")
        dte       = candidate.get("dte", 45)
        opt_type  = candidate.get("option_type", "call").upper()
        strike    = float(candidate.get("strike", 0))
        news_raw  = candidate.get("news_raw_score", 5)   # 0-83 aus news_screener
        cot_net   = candidate.get("cot_net", 0)          # COT Net-Commercial
        iv        = candidate.get("iv_pct", 30) / 100    # annualisiert

        sigma_daily, current_price, sector = self._get_market_params(ticker)

        if current_price <= 0 or strike <= 0:
            return {**candidate, "mirofish_score": 0,
                    "mirofish_confidence": "none",
                    "agent_consensus": "no_data"}

        # Sektor-Adjustierung
        vol_mult  = SECTOR_VOL_MULT.get(sector, 1.0)
        sigma_adj = sigma_daily * vol_mult

        # Adoption-Drift aus News-Score (0-83 → 0-0.008 täglich)
        base_alpha = (news_raw / 83.0) * 0.008
        # COT-Einfluss: positive net = bullish
        cot_alpha  = np.sign(cot_net) * min(abs(cot_net) / 1_000_000, 0.003)

        direction  = "BULLISH" if opt_type == "CALL" else "BEARISH"
        total_alpha = base_alpha + cot_alpha
        if direction == "BEARISH":
            total_alpha = -total_alpha

        # Narrative-Decay
        decay_rate = NARRATIVE_DECAY[self._decay_bucket(dte)]

        # Target: Option muss ITM werden → Strike muss erreicht werden
        target_price = strike

        # Monte-Carlo — vektorisiert (100k Pfade in ~0.3s statt 1.8s)
        rng    = np.random.default_rng(seed=42)
        n_days = min(dte, 180)

        # Drift-Vektor: täglich abnehmend
        alphas = np.array([
            total_alpha * np.exp(-decay_rate * d)
            for d in range(n_days)
        ])

        # Alle Pfade auf einmal: (N_PATHS × n_days)
        Z            = rng.standard_normal((N_PATHS, n_days))
        daily_returns = alphas[np.newaxis, :] + sigma_adj * Z
        log_returns   = np.log1p(daily_returns)
        prices        = current_price * np.exp(np.cumsum(log_returns, axis=1))

        # Pfad trifft Gate wenn irgendwann Strike erreicht
        if direction == "BULLISH":
            hit = np.any(prices >= target_price, axis=1)
        else:
            hit = np.any(prices <= target_price, axis=1)

        hit_rate = float(hit.mean())

        # Score 0-100
        mirofish_score = round(hit_rate * 100)

        if hit_rate >= 0.75:
            confidence = "high"
        elif hit_rate >= 0.60:
            confidence = "medium"
        elif hit_rate >= 0.40:
            confidence = "low"
        else:
            confidence = "none"

        consensus = "bullish" if direction == "BULLISH" else "bearish"

        log.info(f"  [{ticker} {opt_type} {strike}] "
                 f"hit_rate={hit_rate:.1%} score={mirofish_score} "
                 f"({'PASS' if hit_rate >= THRESHOLD else 'FAIL'})")

        return {
            **candidate,
            "mirofish_score":      mirofish_score,
            "mirofish_confidence": confidence,
            "agent_consensus":     consensus,
            "simulation": {
                "hit_rate":      round(hit_rate, 4),
                "n_paths":       N_PATHS,
                "n_days":        n_days,
                "target_price":  round(target_price, 2),
                "current_price": round(current_price, 2),
                "sigma_adj":     round(sigma_adj, 4),
                "sector":        sector,
                "direction":     direction,
            },
        }

    def _run_one_safe(self, candidate):
        """Wrapper mit Timeout-Schutz."""
        sym = candidate.get("symbol", "?")
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(self._simulate_one, candidate)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeout:
                print(f"    Mirofish timeout: {sym}")
                return {**candidate, "mirofish_score": 0,
                        "mirofish_confidence": "none",
                        "agent_consensus": "timeout"}
            except Exception as e:
                print(f"    Mirofish error {sym}: {e}")
                return {**candidate, "mirofish_score": 0,
                        "mirofish_confidence": "none",
                        "agent_consensus": "error"}

    def check_all(self, candidates, raw_data):
        """
        Parallel mit max_workers=4.
        Kandidaten bekommen COT-Daten aus raw_data injiziert.
        """
        if not candidates:
            return [], 0

        # COT-Daten pro Segment für Drift-Berechnung
        cot_map = {}
        for seg, cot in raw_data.get("cot", {}).items():
            cot_map[seg] = cot.get("net_commercial", 0)

        # News-Raw-Score pro Segment
        news_map = {}
        seg_scores = raw_data.get("segment_scores", {})
        for seg, sd in seg_scores.items():
            news_map[seg] = sd.get("news_raw", 5)

        # Kandidaten anreichern
        enriched = []
        for c in candidates:
            seg = c.get("segment", "")
            enriched.append({
                **c,
                "cot_net":        cot_map.get(seg, 0),
                "news_raw_score": news_map.get(seg, 5),
            })

        print(f"  Mirofish: {len(enriched)} Kandidaten "
              f"({self.workers} parallel, {self.timeout}s timeout)")

        results  = []
        timeouts = 0

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._run_one_safe, c): c for c in enriched}
            for future in futures:
                result = future.result()
                results.append(result)
                if result.get("agent_consensus") in ("timeout", "error"):
                    timeouts += 1

        results.sort(key=lambda x: x.get("mirofish_score", 0), reverse=True)
        thr     = self.cfg["thresholds"]["mirofish_score_min"]
        passed  = sum(1 for r in results if r.get("mirofish_score", 0) > thr)
        print(f"  Mirofish: {passed} passed gate (>{thr}), {timeouts} timeouts")

        return results, timeouts
