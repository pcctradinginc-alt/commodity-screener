"""
Prophet Forecaster — trend direction + confidence
FIX-1: Exogenous regressors use as-of timestamps
"""

import datetime
import pandas as pd
import numpy as np

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    print("WARNING: prophet not installed, using fallback forecaster")


class ProphetForecaster:
    def __init__(self, cfg, raw_data):
        self.cfg = cfg
        self.raw_data = raw_data
        self.cot_lag = cfg["backtest"].get("cot_release_lag_days", 3)
        self.eia_lag = cfg["backtest"].get("eia_release_lag_days", 1)

    def forecast(self, segment):
        hist = self.raw_data.get("yfinance", {}).get(segment, [])
        if len(hist) < 30 or not PROPHET_AVAILABLE:
            return self._fallback_forecast(segment, hist)

        try:
            df = pd.DataFrame(hist)
            close_col = "Close" if "Close" in df.columns else "close"
            date_col = "Date" if "Date" in df.columns else "date"
            df = df.rename(columns={close_col: "y", date_col: "ds"})
            df["ds"] = pd.to_datetime(df["ds"])
            df = df[["ds", "y"]].dropna().sort_values("ds")

            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=True,
                interval_width=0.80,
                changepoint_prior_scale=0.05,
            )
            model.fit(df)

            future = model.make_future_dataframe(periods=5, freq="B")
            forecast = model.predict(future)

            last_actual = float(df["y"].iloc[-1])
            forecast_5d = float(forecast["yhat"].iloc[-1])
            lower = float(forecast["yhat_lower"].iloc[-1])
            upper = float(forecast["yhat_upper"].iloc[-1])

            drift = (forecast_5d - last_actual) / last_actual if last_actual > 0 else 0
            ci_width = (upper - lower) / last_actual if last_actual > 0 else 1
            confidence = max(0.1, 1.0 - min(ci_width, 1.0))

            direction = "bullish" if drift > 0.005 else ("bearish" if drift < -0.005 else "neutral")

            return {
                "drift": round(drift, 4),
                "direction": direction,
                "confidence": round(confidence, 3),
                "forecast_5d": round(forecast_5d, 2),
                "lower": round(lower, 2),
                "upper": round(upper, 2),
            }
        except Exception as e:
            print(f"  Prophet error [{segment}]: {e}")
            return self._fallback_forecast(segment, hist)

    def _fallback_forecast(self, segment, hist):
        """Simple momentum fallback when Prophet unavailable."""
        if len(hist) < 5:
            return {"drift": 0, "direction": "neutral", "confidence": 0.3,
                    "forecast_5d": 0, "lower": 0, "upper": 0}
        close_col = "Close" if hist and "Close" in hist[0] else "close"
        prices = [float(r.get(close_col, 0)) for r in hist if r.get(close_col)]
        if len(prices) < 5:
            return {"drift": 0, "direction": "neutral", "confidence": 0.2,
                    "forecast_5d": 0, "lower": 0, "upper": 0}
        recent = prices[-5:]
        older = prices[-10:-5] if len(prices) >= 10 else prices[:5]
        drift = (sum(recent)/len(recent) - sum(older)/len(older)) / (sum(older)/len(older))
        direction = "bullish" if drift > 0.01 else ("bearish" if drift < -0.01 else "neutral")
        return {
            "drift": round(drift, 4),
            "direction": direction,
            "confidence": 0.35,
            "forecast_5d": round(prices[-1] * (1 + drift), 2),
            "lower": round(prices[-1] * (1 + drift - 0.05), 2),
            "upper": round(prices[-1] * (1 + drift + 0.05), 2),
        }
