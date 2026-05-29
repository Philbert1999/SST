"""Common strategy contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd


@dataclass
class StrategyResult:
    code: str
    name: str
    strategy: str
    signal: str
    score: float
    reason: str
    risk: str
    latest_price: float | None = None
    pct_change: float | None = None
    turnover_amount: float | None = None
    sector: str = ""
    scan_time: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        if not data["scan_time"]:
            data["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return data


class BaseStrategy(ABC):
    name = "BaseStrategy"
    display_name = "基础策略"

    def __init__(self, weight: float = 1.0) -> None:
        self.weight = weight

    @abstractmethod
    def evaluate(self, stock: pd.Series, history: pd.DataFrame, context: dict) -> StrategyResult | None:
        """Return a signal result or None when the stock does not match."""

    @staticmethod
    def _latest_meta(stock: pd.Series) -> dict:
        return {
            "code": str(stock.get("code", "")),
            "name": str(stock.get("name", "")),
            "latest_price": stock.get("latest_price"),
            "pct_change": stock.get("pct_change"),
            "turnover_amount": stock.get("turnover_amount"),
            "sector": str(stock.get("sector", "")),
        }
