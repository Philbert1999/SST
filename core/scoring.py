"""Result scoring and aggregation helpers."""

from __future__ import annotations

import pandas as pd


def normalize_results(results: list[dict]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    return df.sort_values(["score", "pct_change"], ascending=[False, False], na_position="last").reset_index(drop=True)


def aggregate_by_stock(results: pd.DataFrame) -> pd.DataFrame:
    """Build a stock-level watchlist from strategy-level signals."""
    if results.empty:
        return pd.DataFrame()

    grouped = (
        results.groupby(["code", "name"], as_index=False)
        .agg(
            total_score=("score", "sum"),
            avg_score=("score", "mean"),
            signal_count=("strategy", "count"),
            strategies=("strategy", lambda s: " / ".join(sorted(set(map(str, s))))),
            latest_price=("latest_price", "last"),
            pct_change=("pct_change", "last"),
            turnover_amount=("turnover_amount", "last"),
            sector=("sector", "last"),
            reasons=("reason", lambda s: "；".join(map(str, s))),
            risks=("risk", lambda s: "；".join(sorted(set(map(str, s))))),
        )
        .sort_values(["total_score", "signal_count"], ascending=[False, False])
        .reset_index(drop=True)
    )
    grouped["total_score"] = grouped["total_score"].round(2)
    grouped["avg_score"] = grouped["avg_score"].round(2)
    return grouped
