"""
PyCOT Analyzer v6 — 3-Jahres-Historie, cot_code aus Config, robustes Spalten-Parsing
"""

import cot_reports as cot
import pandas as pd
import datetime


# Fallback market-name map wenn kein cot_code konfiguriert
_MARKET_NAME_MAP = {
    "USO":  "CRUDE OIL, LIGHT SWEET",
    "XLE":  "CRUDE OIL, LIGHT SWEET",
    "CORN": "CORN",
    "SOYB": "SOYBEANS",
    "WEAT": "WHEAT",
    "GLD":  "GOLD",
    "SLV":  "SILVER",
    "COPX": "COPPER",
    "UNG":  "NATURAL GAS",
}


class PyCOTAnalyzer:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self._df_cache = None  # loaded once per run
        print("  ✅ PyCOT Analyzer v6 geladen (3-Jahres-Historie, cot_code-Lookup)")

    def _load_multi_year(self):
        """Load 3 years of legacy_fut data and cache for the run."""
        if self._df_cache is not None:
            return self._df_cache

        current_year = datetime.datetime.now().year
        dfs = []
        for yr in range(current_year - 2, current_year + 1):
            try:
                df_yr = cot.cot_year(yr, cot_report_type="legacy_fut")
                dfs.append(df_yr)
                print(f"  [COT] Loaded {yr}: {len(df_yr)} rows")
            except Exception as e:
                print(f"  [COT] Could not load {yr}: {e}")

        if not dfs:
            self._df_cache = pd.DataFrame()
        else:
            self._df_cache = pd.concat(dfs, ignore_index=True)

        return self._df_cache

    def get_cot_data(self, ticker: str, cot_cfg: dict = None):
        cot_cfg = cot_cfg or {}
        try:
            df = self._load_multi_year()
            if df.empty:
                return self._default_response()

            # --- Locate market rows ---
            market_data = pd.DataFrame()
            match_method = "none"

            # 1. Try cot_code from config (most reliable — immune to name changes)
            cot_code = cot_cfg.get("cot_code", "")
            if cot_code:
                for col in ["CFTC_Commodity_Code", "Contract_Market_Code",
                            "CFTC_Market_Code", "Commodity_Code"]:
                    if col in df.columns:
                        mask = df[col].astype(str).str.strip() == str(cot_code).strip()
                        if mask.any():
                            market_data = df[mask].copy()
                            match_method = f"code '{cot_code}' via {col}"
                            break

            # 2. Fallback: market name keyword search (warn — names can change over time)
            if market_data.empty:
                if not cot_code:
                    print(f"  [COT] ⚠️  {ticker}: no cot_code configured — returning neutral default")
                    return self._default_response()
                market_name = _MARKET_NAME_MAP.get(ticker.upper(), "")
                if market_name:
                    for col in ["Market_and_Exchange_Names", "Market and Exchange Names",
                                "market_and_exchange_names"]:
                        if col in df.columns:
                            mask = df[col].str.contains(market_name, case=False, na=False)
                            if mask.any():
                                market_data = df[mask].copy()
                                match_method = f"name-fallback '{market_name}'"
                                print(f"  [COT] ⚠️  {ticker}: cot_code '{cot_code}' not found — name fallback active (fragile)")
                                break

            if not market_data.empty:
                print(f"  [COT] {ticker}: matched via {match_method} ({len(market_data)} rows)")

            if market_data.empty:
                print(f"  [COT] {ticker}: kein Match gefunden → Default")
                return self._default_response()

            # --- Coerce numeric columns ---
            long_col  = self._find_col(market_data, ["Commercial Positions-Long (All)",
                                                       "Comm_Positions_Long_All",
                                                       "commercial_positions_long_all"])
            short_col = self._find_col(market_data, ["Commercial Positions-Short (All)",
                                                       "Comm_Positions_Short_All",
                                                       "commercial_positions_short_all"])
            oi_col    = self._find_col(market_data, ["Open Interest (All)",
                                                       "Open_Interest_All",
                                                       "open_interest_all"])
            chg_long  = self._find_col(market_data, ["Change in Commercial-Long (All)",
                                                       "Change_in_Comm_Long_All"])
            chg_short = self._find_col(market_data, ["Change in Commercial-Short (All)",
                                                       "Change_in_Comm_Short_All"])
            date_col  = self._find_col(market_data, ["As of Date in Form YYMMDD",
                                                       "Report_Date_as_YYYY-MM-DD",
                                                       "as_of_date_in_form_yymmdd"])

            for col in [long_col, short_col, oi_col, chg_long, chg_short]:
                if col:
                    market_data[col] = pd.to_numeric(market_data[col], errors="coerce").fillna(0)

            # Sort by date descending
            if date_col:
                market_data = market_data.sort_values(date_col, ascending=False)

            latest    = market_data.iloc[0]
            long_com  = float(latest.get(long_col, 0) if long_col else 0)
            short_com = float(latest.get(short_col, 0) if short_col else 0)
            net_com   = long_com - short_com
            total_oi  = float(latest.get(oi_col, 1) if oi_col else 1) or 1

            # Momentum: week-over-week change in net commercial
            mom_long  = float(latest.get(chg_long, 0) if chg_long else 0)
            mom_short = float(latest.get(chg_short, 0) if chg_short else 0)
            momentum  = (mom_long - mom_short) / 1000.0

            # Commercial OI ratio (signed: negative = net short = hedgers dominant)
            commercial_oi_ratio = (net_com / total_oi) * 100

            # Z-score over full history (up to 3 years)
            if long_col and short_col:
                hist_net = market_data[long_col] - market_data[short_col]
            else:
                hist_net = pd.Series([net_com])

            z_score = 0.0
            if len(hist_net) > 10 and hist_net.std() > 0:
                z_score = (net_com - hist_net.mean()) / hist_net.std()

            # COT Index: percentile rank (0–100)
            if len(hist_net) > 10:
                cot_index = float((hist_net < net_com).mean() * 100)
            else:
                cot_index = 50.0 + z_score * 15

            # Signal logic — z_score is primary gate; OI-Ratio too unstable across markets
            # (crude oil OI is enormous → ratios always tiny; gold OI smaller → ratios larger)
            if z_score > 1.5 and momentum > 20:
                signal, strength_score = "Strong Bullish", 2.5
            elif z_score > 1.0:
                signal, strength_score = "Bullish", 1.8
            elif z_score > 0.4:
                signal, strength_score = "Mild Bullish", 1.3
            elif z_score < -1.5 and momentum < -20:
                signal, strength_score = "Strong Bearish", 0.3
            elif z_score < -1.0:
                signal, strength_score = "Bearish", 0.6
            elif z_score < -0.4:
                signal, strength_score = "Mild Bearish", 0.8
            else:
                signal, strength_score = "Neutral", 1.0

            result = {
                "cot_index":            round(cot_index, 1),
                "commercial_oi_ratio":  round(commercial_oi_ratio, 1),
                "net_commercial":       int(net_com),
                "momentum":             round(momentum, 2),
                "z_score":              round(z_score, 2),
                "signal_strength":      signal,
                "strength_score":       strength_score,
                "history_rows":         len(market_data),
                "match_method":         match_method,
            }
            print(f"  [COT] {ticker} → {signal} | z={z_score:.2f} | "
                  f"OI-Ratio={commercial_oi_ratio:.1f}% | "
                  f"rows={len(market_data)} | via {match_method}")
            return result

        except Exception as e:
            print(f"  ❌ PyCOT v6 Error für {ticker}: {e}")
            return self._default_response()

    def _find_col(self, df, candidates):
        """Return first matching column name (case-insensitive fallback)."""
        cols_lower = {c.lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
            if candidate.lower() in cols_lower:
                return cols_lower[candidate.lower()]
        return None

    def _default_response(self):
        return {
            "cot_index":           50.0,
            "commercial_oi_ratio": 0.0,
            "net_commercial":      0,
            "momentum":            0.0,
            "z_score":             0.0,
            "signal_strength":     "Neutral",
            "strength_score":      1.0,
            "history_rows":        0,
        }
