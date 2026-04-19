"""
Backtest Engine – robustes Datum-Handling für yfinance
"""

import pandas as pd

class BacktestPandas:
    def find_similar_real(self, candidate: dict):
        contract_sym = candidate.get("symbol", "")
        if not contract_sym:
            return {"win_rate": 0.48, "n": 0}

        try:
            # Historische Optionsdaten holen
            df = pd.DataFrame(candidate.get("historical_data", []))
            if df.empty:
                return {"win_rate": 0.48, "n": 0}

            # Robustes Datum-Handling (yfinance Index oder Spalte)
            if "Date" not in df.columns:
                df = df.reset_index()

            date_col = None
            for possible in ["Date", "Datetime", "index"]:
                if possible in df.columns:
                    date_col = possible
                    break

            if date_col:
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.rename(columns={date_col: "Date"})

            # Weiter mit deiner bestehenden Logik (Beispiel-Implementierung)
            n = len(df)
            win_rate = 0.48 if n < 10 else round((df["Close"] > df["Open"]).mean(), 3)

            print(f"    ✅ {n} days for {contract_sym} → win_rate={win_rate}")
            return {"win_rate": win_rate, "n": n}

        except Exception as e:
            print(f"    ⚠️ Backtest error für {contract_sym}: {e}")
            return {"win_rate": 0.48, "n": 0}
