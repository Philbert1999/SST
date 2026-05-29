"""Relative strength scoring strategy."""

from __future__ import annotations

import pandas as pd

from config import DEFAULT_CONFIG
from strategies.base import BaseStrategy, StrategyResult


class StrengthScoreStrategy(BaseStrategy):
    name = "strength_score"
    display_name = "相对强度"

    def __init__(self, lookback: int | None = None, weight: float = 1.0) -> None:
        super().__init__(weight)
        self.lookback = lookback or DEFAULT_CONFIG.strategy.strength_lookback

    def evaluate(self, stock: pd.Series, history: pd.DataFrame, context: dict) -> StrategyResult | None:
        if len(history) < self.lookback + 1:
            return None

        start_close = history["close"].iloc[-self.lookback - 1]
        latest_close = history["close"].iloc[-1]
        if start_close <= 0:
            return None

        return_pct = (latest_close / start_close - 1) * 100
        recent_high = history["high"].iloc[-self.lookback:].max()
        drawdown_from_high = (latest_close / recent_high - 1) * 100 if recent_high > 0 else -99
        turnover_rate = stock.get("turnover_rate", 0) or 0

        if return_pct < 8 or drawdown_from_high < -8:
            return None

        score = min(100, 55 + return_pct * 1.2 + max(drawdown_from_high, -8) + min(turnover_rate, 12) * 1.2) * self.weight
        reason = f"近{self.lookback}日涨幅约{return_pct:.1f}%，距离阶段高点{drawdown_from_high:.1f}%。"
        risk = "强势股波动通常更大；若板块退潮或成交萎缩，评分会快速失真。"
        return StrategyResult(
            **self._latest_meta(stock),
            strategy=self.display_name,
            signal="强度领先",
            score=round(score, 2),
            reason=reason,
            risk=risk,
        )
