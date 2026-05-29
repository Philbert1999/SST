"""Sector heat assisted strategy."""

from __future__ import annotations

import pandas as pd

from config import DEFAULT_CONFIG
from strategies.base import BaseStrategy, StrategyResult


class SectorHotStrategy(BaseStrategy):
    name = "sector_hot"
    display_name = "热点板块"

    def __init__(self, top_n: int | None = None, weight: float = 1.0) -> None:
        super().__init__(weight)
        self.top_n = top_n or DEFAULT_CONFIG.strategy.sector_top_n

    def evaluate(self, stock: pd.Series, history: pd.DataFrame, context: dict) -> StrategyResult | None:
        sector = str(stock.get("sector", "") or "")
        sector_rank = context.get("sector_rank")
        if not sector or sector_rank is None or sector_rank.empty:
            return None

        row = sector_rank[sector_rank["sector"] == sector]
        if row.empty:
            return None

        rank = int(row.iloc[0].get("sector_rank", 999))
        sector_pct = row.iloc[0].get("pct_change", 0)
        stock_pct = stock.get("pct_change", 0) or 0
        if rank > self.top_n or stock_pct <= 0:
            return None

        score = min(100, 52 + (self.top_n - rank + 1) * 1.5 + min(stock_pct, 10) * 3) * self.weight
        reason = f"所属板块「{sector}」热度排名第{rank}，个股同步上涨。"
        risk = "板块热度变化快；仅代表短线关注度，不代表基本面改善。"
        return StrategyResult(
            **self._latest_meta(stock),
            strategy=self.display_name,
            signal="板块共振",
            score=round(score, 2),
            reason=reason,
            risk=risk,
        )
