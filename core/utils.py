"""Shared utility functions."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config import EXPORT_DIR


def history_start_date(days: int) -> date:
    return date.today() - timedelta(days=days * 2)


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def export_csv(df: pd.DataFrame, prefix: str = "scan_results") -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{pd.Timestamp.now():%Y%m%d_%H%M%S}.csv"
    path = EXPORT_DIR / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def format_amount(amount: float | int | None) -> str:
    if amount is None or pd.isna(amount):
        return "-"
    amount = float(amount)
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:.2f}亿"
    if amount >= 10_000:
        return f"{amount / 10_000:.2f}万"
    return f"{amount:.0f}"
