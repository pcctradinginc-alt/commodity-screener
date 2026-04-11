"""
Mirofish Agent Simulation Gate
FIX-2: 60s timeout per candidate + ThreadPoolExecutor parallelization
"""

import sys
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

MIROFISH_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor", "mirofish")
sys.path.insert(0, MIROFISH_PATH)


class MirofishChecker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.timeout = cfg["thresholds"].get("mirofish_timeout_seconds", 60)
        self.workers = cfg["thresholds"].get("mirofish_parallel_workers", 4)
        self.available = self._check_available()

    def _check_available(self):
        try:
            import mirofish
            self.mirofish = mirofish
            print("  Mirofish loaded from vendor/mirofish")
            return True
        except ImportError:
            print("  WARNING: Mirofish not available — will use fallback")
            return False

    def _run_one(self, candidate, raw_data):
        """Run Mirofish simulation for one candidate with timeout enforcement."""
        sym = candidate.get("symbol", "?")
        if not self.available:
            return self._fallback_score(candidate)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.mirofish.simulate,
                candidate,
                raw_data,
            )
            try:
                result = future.result(timeout=self.timeout)
                return {
                    **candidate,
                    "mirofish_score": result.get("score", 0),
                    "mirofish_confidence": result.get("confidence", "low"),
                    "agent_consensus": result.get("consensus", "neutral"),
                }
            except FuturesTimeout:
                print(f"    Mirofish timeout: {sym}")
                return {
                    **candidate,
                    "mirofish_score": 0,
                    "mirofish_confidence": "none",
                    "agent_consensus": "timeout",
                    "mirofish_error": "timeout",
                }
            except Exception as e:
                print(f"    Mirofish error {sym}: {e}")
                return {
                    **candidate,
                    "mirofish_score": 0,
                    "mirofish_confidence": "none",
                    "agent_consensus": "error",
                    "mirofish_error": str(e),
                }

    def _fallback_score(self, candidate):
        """
        Fallback when Mirofish unavailable.
        Uses edge_score as proxy — all candidates pass to Claude Opus.
        """
        edge = candidate.get("edge_score", 50)
        score = min(100, max(0, edge * 0.8 + 20))
        return {
            **candidate,
            "mirofish_score": round(score),
            "mirofish_confidence": "low",
            "agent_consensus": "fallback",
        }

    def check_all(self, candidates, raw_data):
        """
        FIX-2: Run all candidates in parallel with max_workers=4.
        Each candidate has individual 60s timeout.
        Effective runtime: len(candidates) / workers * timeout_seconds
        For 20 candidates: 20/4 * 60s = 5 minutes max.
        """
        if not candidates:
            return [], 0

        print(f"  Running Mirofish on {len(candidates)} candidates "
              f"({self.workers} parallel, {self.timeout}s timeout each)")

        results = []
        timeouts = 0

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {
                pool.submit(self._run_one, c, raw_data): c
                for c in candidates
            }
            for future in futures:
                result = future.result()
                results.append(result)
                if result.get("mirofish_error") == "timeout":
                    timeouts += 1

        results.sort(key=lambda x: x.get("mirofish_score", 0), reverse=True)
        passed = sum(1 for r in results if r.get("mirofish_score", 0) > self.cfg["thresholds"]["mirofish_score_min"])
        print(f"  Mirofish: {passed} passed gate, {timeouts} timeouts")

        return results, timeouts
