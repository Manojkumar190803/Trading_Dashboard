from __future__ import annotations

import pandas as pd

from core.models import StrategyConfig


def compute_rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_indicators(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    data = df.copy()
    data["ema13"] = data["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    data["ema20"] = data["close"].ewm(span=cfg.ema_mid, adjust=False).mean()
    data["ema50"] = data["close"].ewm(span=cfg.ema_slow, adjust=False).mean()

    data["session_date"] = data["datetime"].dt.date
    pv = data["close"] * data["volume"]
    data["vwap"] = (
        pv.groupby(data["session_date"]).cumsum()
        / data["volume"].groupby(data["session_date"]).cumsum()
    )

    data["rsi3"] = compute_rsi(data["close"], cfg.rsi_length)
    return data


def is_strong_green_candle(row: pd.Series, threshold: float = 0.9) -> bool:
    total_range = row["high"] - row["low"]
    if total_range <= 0:
        return False
    body = row["close"] - row["open"]
    return body > 0 and (body / total_range) >= threshold


def is_hammer_candle(row: pd.Series) -> bool:
    total_range = row["high"] - row["low"]
    if total_range <= 0:
        return False
    body = abs(row["close"] - row["open"])
    if body == 0:
        return False
    lower_wick = min(row["open"], row["close"]) - row["low"]
    upper_wick = row["high"] - max(row["open"], row["close"])
    return lower_wick >= 2 * body and upper_wick <= body
