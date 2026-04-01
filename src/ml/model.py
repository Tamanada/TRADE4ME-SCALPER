"""
PriceModel — XGBoost classifier for price direction prediction.
"""

import logging
import os
import numpy as np
import pandas as pd

logger = logging.getLogger("trade4me")

try:
    import xgboost as xgb
    import joblib
    HAS_ML = True
except ImportError:
    HAS_ML = False


class PriceModel:
    def __init__(self, model_path: str = "data/ml_model.pkl"):
        self.model_path = model_path
        self.model = None
        self.is_trained = False

        if not HAS_ML:
            logger.warning("xgboost/joblib not installed — ML disabled")
            return

        if os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                self.is_trained = True
                logger.info("ML model loaded from disk")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")

        if self.model is None:
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                objective="binary:logistic",
                eval_metric="logloss",
                use_label_encoder=False,
            )

    def train(self, df: pd.DataFrame, feature_columns: list[str], min_samples: int = 100) -> bool:
        if not HAS_ML:
            return False
        if len(df) < min_samples:
            logger.warning(f"Not enough data for training: {len(df)} < {min_samples}")
            return False

        try:
            # Target: 1 if next candle closes higher, 0 otherwise
            df = df.copy()
            df["target"] = (df["close"].shift(-1) > df["close"]).astype(int)
            df = df.dropna(subset=["target"] + feature_columns)

            X = df[feature_columns].values
            y = df["target"].values

            if len(X) < min_samples:
                return False

            # Train/test split (80/20)
            split = int(len(X) * 0.8)
            X_train, X_test = X[:split], X[split:]
            y_train, y_test = y[:split], y[split:]

            self.model.fit(X_train, y_train)
            accuracy = self.model.score(X_test, y_test)

            os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
            joblib.dump(self.model, self.model_path)
            self.is_trained = True

            logger.info(f"ML model trained: accuracy={accuracy:.3f} on {len(X)} samples")
            return True
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return False

    def predict(self, df: pd.DataFrame, feature_columns: list[str]) -> tuple[str, float]:
        """Returns (direction, confidence) where direction is 'up' or 'down'."""
        if not HAS_ML or not self.is_trained:
            return "neutral", 0.0

        try:
            latest = df[feature_columns].iloc[-1:].values
            proba = self.model.predict_proba(latest)[0]

            # proba[0] = P(down), proba[1] = P(up)
            if proba[1] > 0.5:
                return "up", float(proba[1])
            else:
                return "down", float(proba[0])
        except Exception as e:
            logger.debug(f"Prediction failed: {e}")
            return "neutral", 0.0
