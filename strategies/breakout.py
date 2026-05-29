"""Price breakout strategy."""

from __future__ import annotations

import pandas as pd

from config import DEFAULT_CONFIG
from strategies.base import BaseStrategy, StrategyResult


class BreakoutStrategy(BaseStrategy):
    name = "breakout"
    display_name = "放量突破"

    def __init__(self, window: int | None = None, volume_ratio: float | None = None, weight: float = 1.0) -> None:
        super().__init__(weight)
        self.window = window or DEFAULT_CONFIG.strategy.breakout_window
        self.volume_ratio = volume_ratio or DEFAULT_CONFIG.strategy.breakout_volume_ratio

    def evaluate(self, stock: pd.Series, history: pd.DataFrame, context: dict) -> StrategyResult | None:
        if len(history) < self.window + 2:
            return None

        latest = history.iloc[-1]
        previous_window = history.iloc[-self.window - 1 : -1]
        recent_high = previous_window["high"].max()
        avg_volume = previous_window["volume"].mean()
        if avg_volume <= 0 or pd.isna(recent_high):
            return None

        price_break = latest["close"] > recent_high
        volume_ok = latest["volume"] >= avg_volume * self.volume_ratio
        if not (price_break and volume_ok):
            return None

        breakout_pct = (latest["close"] / recent_high - 1) * 100
        vol_ratio = latest["volume"] / avg_volume
        score = min(100, 62 + breakout_pct * 5 + min(vol_ratio, 3) * 8) * self.weight
        risk = "突破后若回落至前高下方，需警惕假突破；短线涨幅过大时不宜追高。"
        reason = f"收盘价突破近{self.window}日高点，量能约为均量{vol_ratio:.2f}倍。"
        return StrategyResult(
            **self._latest_meta(stock),
            strategy=self.display_name,
            signal="突破确认",
            score=round(score, 2),
            reason=reason,
            risk=risk,
        )
