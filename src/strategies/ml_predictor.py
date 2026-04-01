"""
MLPredictorStrategy — XGBoost price direction prediction as a strategy.
"""

import time
import pandas as pd
from src.strategies.base import BaseStrategy, Signal, TradeSignal
from src.ml.model import PriceModel
from src.ml.features import build_features, get_feature_columns


class MLPredictorStrategy(BaseStrategy):
    def __init__(self, strat_config: dict = None, ml_config: dict = None):
        super().__init__("ml_predictor", strat_config)
        ml_config = ml_config or {}
        self.confidence_threshold = self.config.get(
            "confidence_threshold",
            ml_config.get("confidence_threshold", 0.65),
        )
        self.model = PriceModel(
            model_path=ml_config.get("model_path", "data/ml_model.pkl")
        )
        self.retrain_interval = ml_config.get("retrain_interval_hours", 24) * 3600
        self.min_training_samples = ml_config.get("min_training_samples", 100)
        self._last_train_time = 0

    def _maybe_retrain(self, df: pd.DataFrame):
        now = time.time()
        if now - self._last_train_time < self.retrain_interval and self.model.is_trained:
            return
        df_features = build_features(df)
        success = self.model.train(df_features, get_feature_columns(), self.min_training_samples)
        if success:
            self._last_train_time = now

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if not self._validate_data(df, min_rows=self.min_training_samples):
            return TradeSignal(Signal.HOLD, symbol, "ML: insufficient data")

        self._maybe_retrain(df)

        if not self.model.is_trained:
            return TradeSignal(Signal.HOLD, symbol, "ML: model not trained")

        df_features = build_features(df)
        direction, confidence = self.model.predict(df_features, get_feature_columns())

        if confidence < self.confidence_threshold:
            return TradeSignal(
                Signal.HOLD, symbol,
                f"ML: {direction} (conf={confidence:.2f} < {self.confidence_threshold})",
            )

        price = df.iloc[-1]["close"]

        if direction == "up":
            return TradeSignal(
                Signal.BUY, symbol,
                f"ML: predict UP (conf={confidence:.2f})",
                strength=confidence, price=price,
            )
        elif direction == "down":
            return TradeSignal(
                Signal.SELL, symbol,
                f"ML: predict DOWN (conf={confidence:.2f})",
                strength=confidence, price=price,
            )

        return TradeSignal(Signal.HOLD, symbol, f"ML: neutral (conf={confidence:.2f})")
