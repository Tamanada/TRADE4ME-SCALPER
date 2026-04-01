"""
Technical indicators — Full suite for multi-timeframe scalping.
"""

import pandas as pd
import numpy as np
import ta


def add_all_indicators(df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    df = df.copy()
    df = add_ma(df)
    df = add_rsi(df)
    df = add_stoch_rsi(df)
    df = add_williams_r(df)
    df = add_mfi(df)
    df = add_connors_rsi(df)
    df = add_macd(df)
    df = add_bollinger(df)
    df = add_volume_indicators(df)
    return df


# ── Moving Averages (MA 7, 21, 50, 100, 200) ──────────────

def add_ma(df: pd.DataFrame) -> pd.DataFrame:
    for period in [7, 21, 50, 100, 200]:
        df[f"ma_{period}"] = df["close"].rolling(window=period, min_periods=1).mean()
        df[f"ema_{period}"] = ta.trend.ema_indicator(df["close"], window=period)
    return df


# ── RSI + Smoothed RSI ────────────────────────────────────

def add_rsi(df: pd.DataFrame, period: int = 14, smooth: int = 14) -> pd.DataFrame:
    df["rsi"] = ta.momentum.rsi(df["close"], window=period)
    df["rsi_sma"] = df["rsi"].rolling(window=smooth, min_periods=1).mean()
    return df


# ── Stochastic RSI (%K and %D) ────────────────────────────

def add_stoch_rsi(df: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> pd.DataFrame:
    stoch = ta.momentum.StochRSIIndicator(df["close"], window=period, smooth1=smooth_k, smooth2=smooth_d)
    df["stoch_rsi_k"] = stoch.stochrsi_k() * 100  # 0-100 scale
    df["stoch_rsi_d"] = stoch.stochrsi_d() * 100
    return df


# ── Williams %R ───────────────────────────────────────────

def add_williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df["williams_r"] = ta.momentum.williams_r(df["high"], df["low"], df["close"], lbp=period)
    return df


# ── Money Flow Index (MFI) ────────────────────────────────

def add_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df["mfi"] = ta.volume.money_flow_index(df["high"], df["low"], df["close"], df["volume"], window=period)
    return df


# ── Connors RSI (RSI + UpDown Streak RSI + %Rank) ────────

def add_connors_rsi(df: pd.DataFrame, rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100) -> pd.DataFrame:
    # Component 1: RSI(3)
    rsi_short = ta.momentum.rsi(df["close"], window=rsi_period)

    # Component 2: Streak RSI — count consecutive up/down days
    streak = pd.Series(0.0, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i - 1]:
            streak.iloc[i] = streak.iloc[i - 1] + 1 if streak.iloc[i - 1] > 0 else 1
        elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
            streak.iloc[i] = streak.iloc[i - 1] - 1 if streak.iloc[i - 1] < 0 else -1
        else:
            streak.iloc[i] = 0
    streak_rsi = ta.momentum.rsi(streak, window=streak_period)

    # Component 3: Percent Rank of price change
    pct_change = df["close"].pct_change()
    pct_rank = pct_change.rolling(window=rank_period, min_periods=1).apply(
        lambda x: (x.iloc[:-1] < x.iloc[-1]).sum() / max(len(x) - 1, 1) * 100, raw=False
    )

    df["crsi"] = (rsi_short + streak_rsi + pct_rank) / 3
    return df


# ── MACD ──────────────────────────────────────────────────

def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd = ta.trend.MACD(df["close"], window_fast=fast, window_slow=slow, window_sign=signal)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()
    return df


# ── Bollinger Bands + %B ──────────────────────────────────

def add_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    bb = ta.volatility.BollingerBands(df["close"], window=period, window_dev=std)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()
    # %B: position of price within the bands (0 = lower, 1 = upper)
    df["bb_pct_b"] = bb.bollinger_pband()
    return df


# ── Volume ────────────────────────────────────────────────

def add_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["volume_sma"] = df["volume"].rolling(window=20, min_periods=1).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma"]
    return df
