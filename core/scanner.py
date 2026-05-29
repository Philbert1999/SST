"""Scanner orchestration."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date
from typing import Iterable

import pandas as pd

from config import AppConfig, DEFAULT_CONFIG
from core.filters import apply_universe_filters
from core.scoring import aggregate_by_stock, normalize_results
from core.utils import history_start_date
from data.data_provider import DataProvider
from strategies.base import BaseStrategy


class StockScanner:
    def __init__(
        self,
        provider: DataProvider,
        strategies: Iterable[BaseStrategy],
        config: AppConfig = DEFAULT_CONFIG,
    ) -> None:
        self.provider = provider
        self.strategies = list(strategies)
        self.config = config
        self.errors: list[dict] = []

    def scan(
        self,
        limit: int | None = None,
        end_date: date | None = None,
        progress_callback=None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Run a batch scan and return strategy results, stock watchlist, universe."""
        self.errors.clear()
        spot = self.provider.get_stock_spot()
        universe = apply_universe_filters(spot, self.config.filter)
        if limit:
            universe = universe.head(limit).copy()

        try:
            sector_rank = self.provider.get_sector_rank()
        except Exception as exc:
            sector_rank = pd.DataFrame()
            self.errors.append({"code": "SECTOR", "name": "板块数据", "error": str(exc)})

        context = {"sector_rank": sector_rank}
        start_date = history_start_date(self.config.scanner.history_days)
        end_date = end_date or date.today()
        all_results: list[dict] = []

        total = len(universe)
        if total == 0:
            return pd.DataFrame(), pd.DataFrame(), universe

        with ThreadPoolExecutor(max_workers=self.config.scanner.max_workers) as executor:
            futures = {
                executor.submit(self._scan_one, row, start_date, end_date, context): idx
                for idx, (_, row) in enumerate(universe.iterrows(), start=1)
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                try:
                    all_results.extend(future.result())
                except Exception as exc:
                    self.errors.append({"code": "UNKNOWN", "name": "", "error": str(exc)})
                if progress_callback:
                    progress_callback(completed, total)

        results = normalize_results(all_results)
        watchlist = aggregate_by_stock(results)
        top_n = self.config.scanner.top_n
        if top_n > 0:
            results = results.head(top_n)
            watchlist = watchlist.head(top_n)
        return results, watchlist, universe

    def _scan_one(self, stock: pd.Series, start_date: date, end_date: date, context: dict) -> list[dict]:
        code = str(stock.get("code", "")).zfill(6)
        name = str(stock.get("name", ""))
        try:
            history = self.provider.get_daily_history(code, start_date=start_date, end_date=end_date)
            time.sleep(self.config.scanner.request_interval_seconds)
            if history.empty:
                return []

            results = []
            for strategy in self.strategies:
                try:
                    result = strategy.evaluate(stock, history, context)
                    if result is not None:
                        results.append(result.to_dict())
                except Exception as exc:
                    self.errors.append({"code": code, "name": name, "strategy": strategy.name, "error": str(exc)})
            return results
        except Exception as exc:
            self.errors.append({"code": code, "name": name, "error": str(exc)})
            return []


def with_runtime_config(base: AppConfig, **kwargs) -> AppConfig:
    """Create a shallow runtime copy for Streamlit controls."""
    filter_cfg = replace(base.filter, **kwargs.get("filter", {}))
    scanner_cfg = replace(base.scanner, **kwargs.get("scanner", {}))
    strategy_cfg = replace(base.strategy, **kwargs.get("strategy", {}))
    return AppConfig(filter=filter_cfg, scanner=scanner_cfg, strategy=strategy_cfg)
