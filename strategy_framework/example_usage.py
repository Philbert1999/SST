"""Minimal example for the strategy framework."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy_framework import (
    StrategyEngine,
    StrengthScoreStrategy,
    StrongPullbackStrategy,
    VolumeBreakoutStrategy,
)


def build_example_data() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    close = [10 + i * 0.08 for i in range(29)] + [13.0]
    data = pd.DataFrame(
        {
            "date": dates,
            "open": [c * 0.98 for c in close],
            "high": [c * 1.02 for c in close],
            "low": [c * 0.97 for c in close],
            "close": close,
            "volume": [10_000_000] * 29 + [18_000_000],
            "amount": [120_000_000] * 29 + [360_000_000],
            "pct_chg": [0.8] * 29 + [4.8],
            "turnover": [2.5] * 29 + [8.0],
        }
    )
    return data


if __name__ == "__main__":
    stock_info = {
        "code": "000001",
        "name": "平安银行",
        "sector": "银行",
        "market": "SZ",
    }
    engine = StrategyEngine(
        [
            VolumeBreakoutStrategy(),
            StrongPullbackStrategy(),
            StrengthScoreStrategy(),
        ]
    )
    for item in engine.evaluate(build_example_data(), stock_info):
        print(item)
