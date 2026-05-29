"""Strategy engine for running multiple strategies on one stock."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from .base import BaseStrategy


class StrategyEngine:
    """Run a list of strategies and isolate per-strategy exceptions."""

    def __init__(self, strategies: Iterable[BaseStrategy]) -> None:
        self.strategies = list(strategies)

    def evaluate(self, df: pd.DataFrame, stock_info: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for strategy in self.strategies:
            try:
                results.append(strategy.evaluate(df, stock_info))
            except Exception as exc:
                results.append(
                    {
                        "code": str(stock_info.get("code", "")),
                        "name": str(stock_info.get("name", "")),
                        "strategy": strategy.display_name,
                        "signal": False,
                        "score": 0,
                        "reasons": [f"策略执行异常：{exc}"],
                        "risks": ["单个策略异常已被隔离，不影响其他策略。"],
                    }
                )
        return results
