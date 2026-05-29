"""Universe filters for A-share candidates."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from config import FilterConfig


def apply_universe_filters(df: pd.DataFrame, cfg: FilterConfig) -> pd.DataFrame:
    """Filter the raw spot universe before running expensive history calls."""
    if df.empty:
        return df

    result = df.copy()
    result["code"] = result["code"].astype(str).str.zfill(6)
    result["name"] = result["name"].astype(str)

    if cfg.exclude_st:
        result = result[~result["name"].str.contains("ST|\\*ST", case=False, regex=True, na=False)]

    if cfg.exclude_delisting_risk:
        result = result[~result["name"].str.contains("退|退市|风险", regex=True, na=False)]

    if cfg.min_listing_days > 0:
        # A-share first-day names often start with N, and registration-board
        # new stocks often start with C during their first trading days.
        result = result[~result["name"].str.contains("^N|^C", regex=True, na=False)]

    if cfg.exclude_beijing_exchange:
        result = result[~result["code"].str.startswith(("8", "4", "9"))]

    result = result[result["latest_price"].fillna(0) >= cfg.min_price]
    result = result[result["latest_price"].fillna(0) <= cfg.max_price]
    result = result[result["turnover_amount"].fillna(0) >= cfg.min_turnover_amount]

    if "listing_date" in result.columns and cfg.min_listing_days > 0:
        today = pd.Timestamp(datetime.now().date())
        listing_days = (today - result["listing_date"]).dt.days
        result = result[listing_days.fillna(9999) >= cfg.min_listing_days]

    return result.reset_index(drop=True)
