"""
Multi-Timeframe Scalping Strategy — BTC/USDT Machine

Timeframes: 15m (direction) → 5m (confirmation) → 1m (entry)
Indicators: Stoch RSI, Williams %R, MFI, CRSI, RSI+SMA, BB %B, MACD
Rule: ALL 3 timeframes must align for entry.
Double direction: LONG and SHORT.
"""

import logging
import pandas as pd
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("trade4me")


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass
class MultiTFSignal:
    direction: Direction
    strength: float          # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str
    tf_15m: Direction        # what 15m says
    tf_5m: Direction         # what 5m says
    tf_1m: Direction         # what 1m says
    indicators: dict         # raw indicator values for logging


class MultiTFScalpStrategy:
    """
    Scans 3 timeframes (15m, 5m, 1m) and enters only when ALL align.

    LONG signal (all must be true):
      - Stoch RSI %K crosses above %D (bullish cross)
      - Williams %R > -50 and rising (leaving oversold zone)
      - MFI rising or > 30
      - CRSI > 40
      - RSI > RSI_SMA (momentum up)
      - BB %B rising toward 0.5+
      - MACD histogram turning positive

    SHORT signal (all must be true):
      - Stoch RSI %K crosses below %D (bearish cross)
      - Williams %R < -50 and falling (leaving overbought zone)
      - MFI falling or < 70
      - CRSI < 60
      - RSI < RSI_SMA (momentum down)
      - BB %B falling toward 0.5-
      - MACD histogram turning negative
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.name = "scalp_multi_tf"

        # Stoch RSI thresholds
        self.stoch_oversold = config.get("stoch_oversold", 20)
        self.stoch_overbought = config.get("stoch_overbought", 80)

        # Williams %R thresholds
        self.wr_buy_threshold = config.get("wr_buy_threshold", -50)
        self.wr_oversold = config.get("wr_oversold", -80)
        self.wr_overbought = config.get("wr_overbought", -20)

        # MFI thresholds
        self.mfi_oversold = config.get("mfi_oversold", 20)
        self.mfi_overbought = config.get("mfi_overbought", 80)

        # CRSI thresholds
        self.crsi_buy = config.get("crsi_buy", 40)
        self.crsi_sell = config.get("crsi_sell", 60)

        # Risk management
        self.sl_pct = config.get("sl_pct", 0.3)   # 0.3% stop loss
        self.tp_pct = config.get("tp_pct", 0.6)   # 0.6% take profit (2:1 R/R)

        # Minimum indicators that must agree (out of 7)
        self.min_agree = config.get("min_agree", 5)

    def analyze_timeframe(self, df: pd.DataFrame) -> tuple[Direction, int, dict]:
        """
        Analyze a single timeframe and return direction + score + indicator values.
        Score = number of indicators agreeing (out of 7).
        """
        if len(df) < 50:
            return Direction.NEUTRAL, 0, {}

        c = df.iloc[-1]   # current candle
        p = df.iloc[-2]   # previous candle

        bull_score = 0
        bear_score = 0
        indicators = {}

        # ── 1. Stoch RSI crossover ────────────────────────
        stoch_k = c.get("stoch_rsi_k", 50)
        stoch_d = c.get("stoch_rsi_d", 50)
        prev_k = p.get("stoch_rsi_k", 50)
        prev_d = p.get("stoch_rsi_d", 50)
        indicators["stoch_k"] = stoch_k
        indicators["stoch_d"] = stoch_d

        if prev_k <= prev_d and stoch_k > stoch_d:  # bullish cross
            bull_score += 1
        elif stoch_k < self.stoch_oversold:  # in oversold zone
            bull_score += 1
        if prev_k >= prev_d and stoch_k < stoch_d:  # bearish cross
            bear_score += 1
        elif stoch_k > self.stoch_overbought:
            bear_score += 1

        # ── 2. Williams %R ────────────────────────────────
        wr = c.get("williams_r", -50)
        prev_wr = p.get("williams_r", -50)
        indicators["williams_r"] = wr

        if wr > self.wr_buy_threshold and wr > prev_wr:  # rising from oversold
            bull_score += 1
        if wr < self.wr_buy_threshold and wr < prev_wr:  # falling from overbought
            bear_score += 1

        # ── 3. MFI ────────────────────────────────────────
        mfi = c.get("mfi", 50)
        prev_mfi = p.get("mfi", 50)
        indicators["mfi"] = mfi

        if mfi > prev_mfi and mfi < self.mfi_overbought:
            bull_score += 1
        if mfi < prev_mfi and mfi > self.mfi_oversold:
            bear_score += 1

        # ── 4. Connors RSI ────────────────────────────────
        crsi = c.get("crsi", 50)
        indicators["crsi"] = crsi

        if crsi > self.crsi_buy:
            bull_score += 1
        if crsi < self.crsi_sell:
            bear_score += 1

        # ── 5. RSI vs RSI SMA ─────────────────────────────
        rsi = c.get("rsi", 50)
        rsi_sma = c.get("rsi_sma", 50)
        indicators["rsi"] = rsi
        indicators["rsi_sma"] = rsi_sma

        if rsi > rsi_sma:
            bull_score += 1
        if rsi < rsi_sma:
            bear_score += 1

        # ── 6. BB %B ──────────────────────────────────────
        bb_pct = c.get("bb_pct_b", 0.5)
        prev_bb = p.get("bb_pct_b", 0.5)
        indicators["bb_pct_b"] = bb_pct

        if bb_pct > prev_bb and bb_pct < 0.8:  # rising but not overbought
            bull_score += 1
        if bb_pct < prev_bb and bb_pct > 0.2:  # falling but not oversold
            bear_score += 1

        # ── 7. MACD histogram ─────────────────────────────
        macd_hist = c.get("macd_histogram", 0)
        prev_hist = p.get("macd_histogram", 0)
        indicators["macd_hist"] = macd_hist

        if macd_hist > prev_hist:  # histogram increasing
            bull_score += 1
        if macd_hist < prev_hist:  # histogram decreasing
            bear_score += 1

        # ── Direction ─────────────────────────────────────
        indicators["bull_score"] = bull_score
        indicators["bear_score"] = bear_score

        if bull_score >= self.min_agree:
            return Direction.LONG, bull_score, indicators
        elif bear_score >= self.min_agree:
            return Direction.SHORT, bear_score, indicators
        else:
            return Direction.NEUTRAL, max(bull_score, bear_score), indicators

    def analyze(self, df_15m: pd.DataFrame, df_5m: pd.DataFrame, df_1m: pd.DataFrame) -> MultiTFSignal:
        """
        Multi-timeframe analysis.
        15m = direction, 5m = confirmation, 1m = entry.
        ALL must agree for a trade.
        """
        dir_15m, score_15m, ind_15m = self.analyze_timeframe(df_15m)
        dir_5m, score_5m, ind_5m = self.analyze_timeframe(df_5m)
        dir_1m, score_1m, ind_1m = self.analyze_timeframe(df_1m)

        price = df_1m.iloc[-1]["close"] if len(df_1m) > 0 else 0

        # All 3 timeframes must agree
        all_long = dir_15m == Direction.LONG and dir_5m == Direction.LONG and dir_1m == Direction.LONG
        all_short = dir_15m == Direction.SHORT and dir_5m == Direction.SHORT and dir_1m == Direction.SHORT

        if all_long:
            strength = (score_15m + score_5m + score_1m) / 21  # max 7*3=21
            sl = price * (1 - self.sl_pct / 100)
            tp = price * (1 + self.tp_pct / 100)
            return MultiTFSignal(
                direction=Direction.LONG,
                strength=strength,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                reason=f"LONG: 15m({score_15m}/7) 5m({score_5m}/7) 1m({score_1m}/7) = ALL ALIGNED",
                tf_15m=dir_15m, tf_5m=dir_5m, tf_1m=dir_1m,
                indicators={"15m": ind_15m, "5m": ind_5m, "1m": ind_1m},
            )

        elif all_short:
            strength = (score_15m + score_5m + score_1m) / 21
            sl = price * (1 + self.sl_pct / 100)
            tp = price * (1 - self.tp_pct / 100)
            return MultiTFSignal(
                direction=Direction.SHORT,
                strength=strength,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                reason=f"SHORT: 15m({score_15m}/7) 5m({score_5m}/7) 1m({score_1m}/7) = ALL ALIGNED",
                tf_15m=dir_15m, tf_5m=dir_5m, tf_1m=dir_1m,
                indicators={"15m": ind_15m, "5m": ind_5m, "1m": ind_1m},
            )

        else:
            reason = f"NO TRADE: 15m={dir_15m.value}({score_15m}) 5m={dir_5m.value}({score_5m}) 1m={dir_1m.value}({score_1m})"
            return MultiTFSignal(
                direction=Direction.NEUTRAL,
                strength=0,
                entry_price=price,
                stop_loss=0,
                take_profit=0,
                reason=reason,
                tf_15m=dir_15m, tf_5m=dir_5m, tf_1m=dir_1m,
                indicators={"15m": ind_15m, "5m": ind_5m, "1m": ind_1m},
            )
