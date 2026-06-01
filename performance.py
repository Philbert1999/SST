"""Screening snapshot storage and forward-return evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

try:
    from config import SNAPSHOT_DIR
except ImportError:
    from .config import SNAPSHOT_DIR


RETURN_COLUMNS = [f"return_d{i}" for i in range(1, 6)]


@dataclass(frozen=True)
class SnapshotInfo:
    path: Path
    name: str
    rows: int
    signal_date: str
    created_at: str

    def label(self) -> str:
        return f"{self.signal_date} | {self.rows} stocks | {self.name}"


def save_screening_snapshot(results: pd.DataFrame, signal_date, options: dict[str, Any] | None = None) -> Path | None:
    """Save one day's screening results for later quality review."""
    if results is None or results.empty:
        return None

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    signal_date_text = _date_text(signal_date)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"screening_{signal_date_text}_{datetime.now():%H%M%S}.csv"
    path = SNAPSHOT_DIR / filename

    df = results.copy()
    df["signal_date"] = signal_date_text
    df["snapshot_created_at"] = created_at
    if options:
        df["selected_strategies"] = " / ".join(map(str, options.get("selected_strategy_names", [])))
        df["min_price_filter"] = options.get("min_price")
        df["max_price_filter"] = options.get("max_price")
        df["min_amount_filter"] = options.get("min_amount")

    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def list_snapshots(snapshot_dir: Path = SNAPSHOT_DIR) -> list[SnapshotInfo]:
    """List saved screening snapshots, newest first."""
    if not snapshot_dir.exists():
        return []

    items: list[SnapshotInfo] = []
    for path in sorted(snapshot_dir.glob("screening_*.csv"), reverse=True):
        try:
            df = pd.read_csv(path, dtype={"code": str})
            signal_date = str(df.get("signal_date", pd.Series([""])).dropna().iloc[0])
            created_at = str(df.get("snapshot_created_at", pd.Series([""])).dropna().iloc[0])
            items.append(SnapshotInfo(path=path, name=path.name, rows=len(df), signal_date=signal_date, created_at=created_at))
        except Exception:
            continue
    return items


def load_snapshot(path: str | Path) -> pd.DataFrame:
    """Load one screening snapshot."""
    df = pd.read_csv(path, dtype={"code": str})
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def evaluate_snapshot(
    snapshot: pd.DataFrame,
    data_provider,
    horizon: int = 5,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> pd.DataFrame:
    """Evaluate D1-D5 cumulative returns after the screening signal date.

    Returns are measured from the signal day's close to each next trading day's
    close, not intraday highs. Missing future bars are left as NaN.
    """
    if snapshot is None or snapshot.empty:
        return _empty_evaluation()

    rows: list[dict[str, Any]] = []
    total = len(snapshot)
    for index, (_, item) in enumerate(snapshot.iterrows(), start=1):
        code = str(item.get("code", "")).zfill(6)
        signal_date = _parse_signal_date(item)
        if progress_callback:
            progress_callback(index, total, code)

        try:
            history_start = signal_date - timedelta(days=10)
            history_end = signal_date + timedelta(days=max(20, horizon * 4))
            history = data_provider.get_daily_data(code, history_start, history_end)
            rows.append(_evaluate_one(item, history, signal_date, horizon))
        except Exception as exc:
            row = _base_result_row(item)
            row["eval_error"] = str(exc)
            rows.append(row)

    return pd.DataFrame(rows)


def summarize_evaluation(evaluation: pd.DataFrame, horizon: int = 5) -> dict[str, Any]:
    """Build high-level quality metrics from evaluated candidates."""
    horizon = max(1, min(int(horizon), 5))
    if evaluation is None or evaluation.empty:
        return {
            "sample_count": 0,
            "selected_horizon": horizon,
            "avg_return_selected": 0.0,
            "win_rate_selected": 0.0,
            "best_return_selected": 0.0,
            "worst_return_selected": 0.0,
            "avg_return_d5": 0.0,
            "win_rate_d5": 0.0,
            "best_return_d5": 0.0,
            "worst_return_d5": 0.0,
        }

    summary: dict[str, Any] = {"sample_count": len(evaluation), "selected_horizon": horizon}
    for day in range(1, 6):
        col = f"return_d{day}"
        valid = _numeric_column(evaluation, col)
        summary[f"avg_return_d{day}"] = float(valid.mean()) if not valid.empty else 0.0
        summary[f"win_rate_d{day}"] = float((valid > 0).mean() * 100) if not valid.empty else 0.0

    selected = _numeric_column(evaluation, f"return_d{horizon}")
    summary["avg_return_selected"] = summary.get(f"avg_return_d{horizon}", 0.0)
    summary["win_rate_selected"] = summary.get(f"win_rate_d{horizon}", 0.0)
    summary["best_return_selected"] = float(selected.max()) if not selected.empty else 0.0
    summary["worst_return_selected"] = float(selected.min()) if not selected.empty else 0.0

    d5 = _numeric_column(evaluation, "return_d5")
    summary["best_return_d5"] = float(d5.max()) if not d5.empty else 0.0
    summary["worst_return_d5"] = float(d5.min()) if not d5.empty else 0.0
    return summary


def _numeric_column(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric Series for an optional evaluation column."""
    if column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").dropna()


def _evaluate_one(item: pd.Series, history: pd.DataFrame, signal_date: date, horizon: int) -> dict[str, Any]:
    row = _base_result_row(item)
    if history is None or history.empty:
        row["eval_error"] = "no_daily_data"
        return row

    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data = data.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    if data.empty:
        row["eval_error"] = "empty_after_clean"
        return row

    signal_ts = pd.Timestamp(signal_date)
    base_candidates = data[data["date"] <= signal_ts]
    if base_candidates.empty:
        row["eval_error"] = "no_base_bar"
        return row

    base_index = int(base_candidates.index[-1])
    base = data.iloc[base_index]
    base_close = float(base["close"])
    row["base_date"] = base["date"].strftime("%Y-%m-%d")
    row["base_close"] = base_close

    returns: list[float] = []
    for day in range(1, horizon + 1):
        future_index = base_index + day
        if future_index >= len(data) or base_close <= 0:
            row[f"date_d{day}"] = pd.NA
            row[f"close_d{day}"] = pd.NA
            row[f"return_d{day}"] = pd.NA
            continue

        future = data.iloc[future_index]
        ret = (float(future["close"]) / base_close - 1) * 100
        returns.append(ret)
        row[f"date_d{day}"] = future["date"].strftime("%Y-%m-%d")
        row[f"close_d{day}"] = float(future["close"])
        row[f"return_d{day}"] = round(ret, 2)

    valid_returns = [value for value in returns if pd.notna(value)]
    row["max_return_5d"] = round(max(valid_returns), 2) if valid_returns else pd.NA
    row["min_return_5d"] = round(min(valid_returns), 2) if valid_returns else pd.NA
    row["positive_any_5d"] = bool(any(value > 0 for value in valid_returns)) if valid_returns else pd.NA
    row["eval_error"] = ""
    return row


def _base_result_row(item: pd.Series) -> dict[str, Any]:
    return {
        "code": str(item.get("code", "")).zfill(6),
        "name": item.get("name", ""),
        "signal_date": item.get("signal_date", ""),
        "total_score": item.get("total_score", pd.NA),
        "triggered_strategies": item.get("triggered_strategies", ""),
        "base_date": pd.NA,
        "base_close": item.get("close", pd.NA),
        "eval_error": "",
    }


def _parse_signal_date(item: pd.Series) -> date:
    value = item.get("signal_date")
    if pd.isna(value) or not str(value):
        value = item.get("snapshot_created_at", date.today())
    return pd.to_datetime(value).date()


def _date_text(value) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _empty_evaluation() -> pd.DataFrame:
    columns = ["code", "name", "signal_date", "total_score", "triggered_strategies", "base_date", "base_close"]
    for day in range(1, 6):
        columns += [f"date_d{day}", f"close_d{day}", f"return_d{day}"]
    columns += ["max_return_5d", "min_return_5d", "positive_any_5d", "eval_error"]
    return pd.DataFrame(columns=columns)
