"""Base classes and common helpers for strategy evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


REQUIRED_DAILY_COLUMNS = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
    "turnover",
}

REQUIRED_STOCK_INFO_KEYS = {"code", "name", "sector", "market"}


@dataclass(frozen=True)
class EvaluationContext:
    """Normalized data and stock metadata passed to a strategy."""

    df: pd.DataFrame
    stock_info: dict[str, Any]


class BaseStrategy(ABC):
    """Abstract base class for all stock selection strategies."""

    name = "base"
    display_name = "BaseStrategy"

    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def evaluate(self, df: pd.DataFrame, stock_info: dict[str, Any]) -> dict[str, Any]:
        """Validate input, normalize ordering, and run strategy-specific logic."""
        context, invalid_reasons = self._build_context(df, stock_info)
        if invalid_reasons:
            return self._result(stock_info, False, 0, invalid_reasons, ["数据不足或字段缺失，跳过该策略。"])
        return self._evaluate(context)

    @abstractmethod
    def _evaluate(self, context: EvaluationContext) -> dict[str, Any]:
        """Evaluate a normalized single-stock daily bar dataframe."""

    def _build_context(
        self,
        df: pd.DataFrame,
        stock_info: dict[str, Any],
    ) -> tuple[EvaluationContext | None, list[str]]:
        reasons: list[str] = []
        if df is None or df.empty:
            reasons.append("日线数据为空。")
            return None, reasons

        missing_columns = sorted(REQUIRED_DAILY_COLUMNS - set(df.columns))
        if missing_columns:
            reasons.append(f"日线数据缺少字段：{', '.join(missing_columns)}。")

        missing_info = sorted(REQUIRED_STOCK_INFO_KEYS - set(stock_info.keys()))
        if missing_info:
            reasons.append(f"stock_info 缺少字段：{', '.join(missing_info)}。")

        if reasons:
            return None, reasons

        normalized = df.copy()
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        numeric_columns = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
        for column in numeric_columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

        normalized = normalized.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date")
        normalized = normalized.reset_index(drop=True)
        if normalized.empty:
            reasons.append("日线数据清洗后为空。")
            return None, reasons
        return EvaluationContext(normalized, stock_info), []

    def _result(
        self,
        stock_info: dict[str, Any],
        signal: bool,
        score: float,
        reasons: list[str],
        risks: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "code": str(stock_info.get("code", "")),
            "name": str(stock_info.get("name", "")),
            "strategy": self.display_name,
            "signal": bool(signal),
            "score": max(0, min(100, round(float(score), 2))),
            "reasons": reasons,
            "risks": risks or [],
        }

    def _insufficient_data(self, stock_info: dict[str, Any], required_rows: int, actual_rows: int) -> dict[str, Any]:
        return self._result(
            stock_info=stock_info,
            signal=False,
            score=0,
            reasons=[f"数据不足：至少需要 {required_rows} 条日线，当前只有 {actual_rows} 条。"],
            risks=["样本不足时不计算信号，避免误判。"],
        )

    @staticmethod
    def _ma(df: pd.DataFrame, window: int) -> pd.Series:
        return df["close"].rolling(window=window, min_periods=window).mean()

    @staticmethod
    def _price_position_in_range(low: float, high: float, close: float) -> float:
        if high <= low:
            return 0.0
        return (close - low) / (high - low)

    @staticmethod
    def _pct_distance(a: float, b: float) -> float:
        if b == 0 or pd.isna(b):
            return float("inf")
        return abs(a / b - 1) * 100
