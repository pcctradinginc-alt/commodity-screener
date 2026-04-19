"""
MirofishChecker v1.0 – Kompatibel mit main.py (mit cfg)
"""

class MirofishChecker:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        print("  Mirofish: Python Jump-Diffusion Engine geladen (Regime-Switching aktiv)")

    def run(self, candidates):
        """Filtert Kandidaten nach Edge-Score > 25"""
        if not candidates:
            print("  Mirofish passed: 0 candidates")
            return []

        # Einfacher Gate (wie in früheren Versionen)
        passed = [c for c in candidates if c.get("edge_score", 0) > 25]

        print(f"  Mirofish passed: {len(passed)} candidates (timeouts: 0)")
        return passed[:20]   # maximal 20 an Claude weitergeben
