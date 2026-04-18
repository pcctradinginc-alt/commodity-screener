"""
Mirofish Simulation — Pfad-basiertes Gate
MIT MERTON JUMP-DIFFUSION + REGIME-SWITCHING + datetime Import
"""

import logging
import numpy as np
import yfinance as yf
import datetime                               # ← NEU: fehlte vorher
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

log = logging.getLogger(__name__)

N_PATHS   = 100_000
THRESHOLD = 0.25

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

JUMP_PROB_BASE = 0.025
JUMP_PROB_RELEASE = 0.12
JUMP_SIZE_MEAN = 0.0
JUMP_SIZE_STD = 0.045


class MirofishChecker:
    def __init__(self, cfg):
        self.cfg      = cfg
        self.timeout  = cfg["thresholds"].get("mirofish_timeout_seconds", 60)
        self.workers  = cfg["thresholds"].get("mirofish_parallel_workers", 4)
        self.available = True
        print("  Mirofish: Python Jump-Diffusion Engine geladen (Regime-Switching aktiv)")

    # ... (der Rest der Klasse bleibt genau gleich wie in der letzten Version) ...
    # (Um den Antworttext nicht zu lang zu machen, lasse ich die restlichen Methoden hier weg – sie sind identisch mit der letzten Mirofish-Datei, die ich dir gegeben habe.)

    # Wenn du die vollständige Mirofish-Datei noch einmal brauchst, sag einfach „vollständige mirofish_check.py“ und ich schicke sie dir sofort.
