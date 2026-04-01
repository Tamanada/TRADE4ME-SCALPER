"""
FeatureEngineer — Build ML features from OHLCV DataFrame.
"""

import pandas as pd
import ta


FEATURE_COLUMNS = [
    "price_change", "volume_change",
    "price_ma3", "price_ma7", "price_ma20",
    "price_std3", "price_std7",
    "momentum", "rsi", "macd_hist",
    "bb_width", "volume_ratio",
    "hour_of_day", "day_of_week",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Price and volume changes
    df["price_change"] = df["close"].pct_change().fillna(0)
    df["volume_change"] = df["volume"].pct_change().fillna(0)

    # Moving averages
    df["price_ma3"] = df["close"].rolling(3, min_periods=1).mean()
    df["price_ma7"] = df["close"].rolling(7, min_periods=1).mean()
    df["price_ma20"] = df["close"].rolling(20, min_periods=1).mean()

    # Volatility
    df["price_std3"] = df["close"].rolling(3, min_periods=1).std().fillna(0)
    df["price_std7"] = df["close"].rolling(7, min_periods=1).std().fillna(0)

    # Momentum
    df["momentum"] = df["close"] - df["price_ma7"]

    # RSI
    df["rsi"] = ta.momentum.rsi(df["close"], window=14).fillna(50)

    # MACD histogram
    macd = ta.trend.MACD(df["close"])
    df["macd_hist"] = macd.macd_diff().fillna(0)

    # Bollinger Band width
    bb = ta.volatility.BollingerBands(df["close"], window=20)
    df["bb_width"] = bb.bollinger_wband().fillna(0)

    # Volume ratio
    vol_sma = df["volume"].rolling(20, min_periods=1).mean()
    df["volume_ratio"] = (df["volume"] / vol_sma).fillna(1)

    # Temporal features
    if isinstance(df.index, pd.DatetimeIndex):
        df["hour_of_day"] = df.index.hour
        df["day_of_week"] = df.index.dayofweek
    else:
        df["hour_of_day"] = 0
        df["day_of_week"] = 0

    return df


def get_feature_columns() -> list[str]:
    return FEATURE_COLUMNS
