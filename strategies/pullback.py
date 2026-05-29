"""Trend pullback strategy."""

from __future__ import annotations

import pandas as pd

from config import DEFAULT_CONFIG
from strategies.base import BaseStrategy, StrategyResult


class PullbackStrategy(BaseStrategy):
    name = "pullback"
    display_name = "强势回踩"

    def __init__(self, ma_window: int | None = None, max_distance_pct: float | None = None, weight: float = 1.0) -> None:
        super().__init__(weight)
        self.ma_window = ma_window or DEFAULT_CONFIG.strategy.pullback_ma_window
        self.max_distance_pct = max_distance_pct or DEFAULT_CONFIG.strategy.pullback_max_distance_pct

    def evaluate(self, stock: pd.Series, history: pd.DataFrame, context: dict) -> StrategyResult | None:
        if len(history) < self.ma_window + 10:
            return None

        df = history.copy()
        df["ma"] = df["close"].rolling(self.ma_window).mean()
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        ma = latest["ma"]
        if pd.isna(ma) or ma <= 0:
            return None

        ma_rising = df["ma"].iloc[-1] > df["ma"].iloc[-6]
        near_ma = abs(latest["close"] / ma - 1) * 100 <= self.max_distance_pct
        rebound = latest["close"] > latest["open"] and latest["close"] > prev["close"]
        recent_strength = latest["close"] > df["close"].iloc[-20:].min() * 1.08
        if not (ma_rising and near_ma and rebound and recent_strength):
            return None

        distance_pct = abs(latest["close"] / ma - 1) * 100
        score = min(100, 58 + (self.max_distance_pct - distance_pct) * 6 + min(latest["pct_change"], 6) * 4) * self.weight
        reason = f"{self.ma_window}日均线向上，股价回踩均线附近后转强。"
        risk = "回踩策略依赖趋势延续；若放量跌破均线，候选逻辑失效。"
        return StrategyResult(
            **self._latest_meta(stock),
            strategy=self.display_name,
            signal="回踩转强",
            score=round(score, 2),
            reason=reason,
            risk=risk,
        )
