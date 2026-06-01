"""Data provider interfaces for A-share short-term screening."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """Abstract data source contract.

    Concrete providers can wrap AKShare, Tushare, iFinD, local files, or an
    internal market-data service. The rest of the app should depend on this
    interface instead of a vendor SDK directly.
    """

    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """Return stock metadata: code, name, market, is_st, listing_date."""

    @abstractmethod
    def get_daily_data(self, code: str, start_date, end_date, force_refresh: bool = False) -> pd.DataFrame:
        """Return normalized daily bars for one stock."""

    @abstractmethod
    def get_realtime_quotes(self) -> pd.DataFrame:
        """Return normalized realtime A-share quotes."""

    @abstractmethod
    def get_sector_data(self) -> pd.DataFrame:
        """Return normalized sector/industry data."""
