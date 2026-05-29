"""Batch scanner for running short-term strategies on A-share stocks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable

import pandas as pd

try:
    from config import APP_CONFIG
except ImportError:
    from ..config import APP_CONFIG

from .base import BaseStrategy
from .engine import StrategyEngine


logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")


ProgressCallback = Callable[..., None]


@dataclass(frozen=True)
class ScannerFilterConfig:
    """Basic stock-universe filters used before strategy signals are accepted."""

    exclude_st: bool = APP_CONFIG.filter.exclude_st
    exclude_delisting_risk: bool = APP_CONFIG.filter.exclude_delisting_risk
    exclude_star_market: bool = APP_CONFIG.filter.exclude_star_market
    min_listing_days: int = APP_CONFIG.filter.exclude_new_stock_days
    min_price: float = APP_CONFIG.filter.min_price
    max_price: float = APP_CONFIG.filter.max_price
    min_amount: float = APP_CONFIG.filter.min_amount
    overheat_days: int = APP_CONFIG.scanner.overheat_days
    max_recent_gain_pct: float = APP_CONFIG.filter.max_20d_gain
    delisting_keywords: tuple[str, ...] = ("\u9000", "\u9000\u5e02", "\u98ce\u9669")


class StockScanner:
    """Run multiple strategies over a stock list and aggregate true signals."""

    def __init__(
        self,
        stock_list: pd.DataFrame,
        data_provider: Any,
        strategies: Iterable[BaseStrategy],
        start_date,
        end_date,
        filter_config: ScannerFilterConfig | dict[str, Any] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.stock_list = stock_list.copy() if stock_list is not None else pd.DataFrame()
        self.data_provider = data_provider
        self.strategies = list(strategies)
        self.start_date = start_date
        self.end_date = end_date
        self.filter_config = self._build_filter_config(filter_config)
        self.progress_callback = progress_callback
        self.engine = StrategyEngine(self.strategies)
        self.errors: list[dict[str, Any]] = []
        self.skipped: list[dict[str, Any]] = []

    def scan(self) -> pd.DataFrame:
        """Scan all stocks and return aggregated signal=True candidates."""
        if self.stock_list.empty:
            logger.warning("Stock list is empty; scanner returns empty result.")
            return self._empty_result()

        candidates: list[dict[str, Any]] = []
        total = len(self.stock_list)
        logger.info("Start scanning %s stocks with %s strategies.", total, len(self.strategies))

        for index, (_, stock) in enumerate(self.stock_list.iterrows(), start=1):
            stock_info = self._stock_info(stock)
            code = stock_info["code"]
            try:
                meta_skip_reason = self._metadata_filter_reason(stock)
                if meta_skip_reason:
                    self._skip(code, stock_info["name"], meta_skip_reason)
                    self._report_progress(index, total, code, meta_skip_reason)
                    continue

                df = self.data_provider.get_daily_data(code, self.start_date, self.end_date)
                df = self._normalize_daily_data(df)
                daily_skip_reason = self._daily_filter_reason(df)
                if daily_skip_reason:
                    self._skip(code, stock_info["name"], daily_skip_reason)
                    self._report_progress(index, total, code, daily_skip_reason)
                    continue

                signal_results = [item for item in self.engine.evaluate(df, stock_info) if item.get("signal") is True]
                if signal_results:
                    candidates.append(self._merge_stock_results(stock_info, df, signal_results))

                self._report_progress(index, total, code, "done")
            except Exception as exc:
                logger.exception("Failed to scan %s: %s", code, exc)
                self.errors.append({"code": code, "name": stock_info.get("name", ""), "error": str(exc)})
                self._report_progress(index, total, code, "error")

        result = pd.DataFrame(candidates)
        if result.empty:
            logger.info("Scan finished. No signal=True candidate found.")
            return self._empty_result()

        result = result.sort_values("total_score", ascending=False).reset_index(drop=True)
        logger.info("Scan finished. Candidates: %s, skipped: %s, errors: %s", len(result), len(self.skipped), len(self.errors))
        return result

    def _metadata_filter_reason(self, stock: pd.Series) -> str | None:
        cfg = self.filter_config
        code = str(stock.get("code", "")).split(".")[0].zfill(6)
        name = str(stock.get("name", ""))

        if cfg.exclude_star_market and self._is_star_market(code):
            return "\u6392\u9664\u79d1\u521b\u677f\u80a1\u7968"

        is_st = bool(stock.get("is_st", False))
        if cfg.exclude_st and (is_st or self._contains_st(name)):
            return "\u6392\u9664 ST \u80a1\u7968"

        if cfg.exclude_delisting_risk and any(keyword in name for keyword in cfg.delisting_keywords):
            return "\u6392\u9664\u9000\u5e02\u98ce\u9669\u80a1\u7968"

        listing_date = pd.to_datetime(stock.get("listing_date", pd.NaT), errors="coerce")
        if cfg.min_listing_days > 0 and pd.notna(listing_date):
            end = pd.to_datetime(self.end_date)
            listing_days = (end.normalize() - listing_date.normalize()).days
            if listing_days < cfg.min_listing_days:
                return f"\u6392\u9664\u4e0a\u5e02\u4e0d\u8db3 {cfg.min_listing_days} \u5929\u7684\u65b0\u80a1"

        return None

    def _daily_filter_reason(self, df: pd.DataFrame) -> str | None:
        cfg = self.filter_config
        required_rows = cfg.overheat_days + 1
        if df.empty:
            return "\u65e5\u7ebf\u6570\u636e\u4e3a\u7a7a"
        if len(df) < required_rows:
            return f"\u65e5\u7ebf\u6570\u636e\u4e0d\u8db3\uff0c\u81f3\u5c11\u9700\u8981 {required_rows} \u6761"

        latest = df.iloc[-1]
        close = latest.get("close")
        if pd.isna(close) or close < cfg.min_price:
            return f"\u6392\u9664\u80a1\u4ef7\u4f4e\u4e8e {cfg.min_price} \u5143"
        if close > cfg.max_price:
            return f"\u6392\u9664\u80a1\u4ef7\u9ad8\u4e8e {cfg.max_price} \u5143"

        if pd.isna(latest["amount"]) or latest["amount"] < cfg.min_amount:
            return f"\u6392\u9664\u6700\u8fd1\u65e5\u6210\u4ea4\u989d\u4f4e\u4e8e {cfg.min_amount:.0f} \u5143"

        base_close = df.iloc[-cfg.overheat_days - 1]["close"]
        if pd.notna(base_close) and base_close > 0:
            recent_gain_pct = (close / base_close - 1) * 100
            if recent_gain_pct > cfg.max_recent_gain_pct:
                return f"\u6392\u9664\u6700\u8fd1 {cfg.overheat_days} \u65e5\u6da8\u5e45\u8d85\u8fc7 {cfg.max_recent_gain_pct}% \u7684\u8fc7\u70ed\u80a1\u7968"

        return None

    def _merge_stock_results(self, stock_info: dict[str, Any], df: pd.DataFrame, signal_results: list[dict[str, Any]]) -> dict[str, Any]:
        latest = df.iloc[-1]
        strategies = [str(item.get("strategy", "")) for item in signal_results if item.get("strategy")]
        reasons = self._flatten_text_list(item.get("reasons", []) for item in signal_results)
        risks = self._flatten_text_list(item.get("risks", []) for item in signal_results)
        total_score = sum(float(item.get("score", 0) or 0) for item in signal_results)

        return {
            "code": stock_info["code"],
            "name": stock_info["name"],
            "total_score": round(total_score, 2),
            "triggered_strategies": " / ".join(dict.fromkeys(strategies)),
            "reasons": "\uff1b".join(dict.fromkeys(reasons)),
            "risks": "\uff1b".join(dict.fromkeys(risks)),
            "close": latest.get("close"),
            "pct_chg": latest.get("pct_chg"),
            "amount": latest.get("amount"),
            "turnover": latest.get("turnover"),
        }

    def _stock_info(self, stock: pd.Series) -> dict[str, Any]:
        code = str(stock.get("code", "")).split(".")[0].zfill(6)
        return {
            "code": code,
            "name": str(stock.get("name", "")),
            "sector": str(stock.get("sector", "")),
            "market": str(stock.get("market", "")),
        }

    @staticmethod
    def _normalize_daily_data(df: pd.DataFrame) -> pd.DataFrame:
        required_columns = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
        if df is None or df.empty:
            return pd.DataFrame(columns=required_columns)

        normalized = df.copy()
        for column in required_columns:
            if column not in normalized.columns:
                normalized[column] = pd.NA

        normalized = normalized[required_columns].copy()
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        for column in required_columns:
            if column != "date":
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        return normalized.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)

    @staticmethod
    def _contains_st(name: str) -> bool:
        upper_name = name.upper()
        return "ST" in upper_name or "*ST" in upper_name

    @staticmethod
    def _is_star_market(code: str) -> bool:
        return str(code).zfill(6).startswith(("688", "689"))

    @staticmethod
    def _flatten_text_list(groups: Iterable[Any]) -> list[str]:
        flattened: list[str] = []
        for group in groups:
            if group is None:
                continue
            if isinstance(group, str):
                flattened.append(group)
                continue
            try:
                flattened.extend(str(item) for item in group if str(item))
            except TypeError:
                flattened.append(str(group))
        return flattened

    def _skip(self, code: str, name: str, reason: str) -> None:
        logger.debug("Skip %s %s: %s", code, name, reason)
        self.skipped.append({"code": code, "name": name, "reason": reason})

    def _report_progress(self, done: int, total: int, code: str, status: str) -> None:
        if self.progress_callback is None:
            return
        progress = done / total if total else 1.0
        try:
            self.progress_callback(done, total, code, status)
        except TypeError:
            try:
                self.progress_callback(progress)
            except TypeError:
                self.progress_callback(done, total)

    @staticmethod
    def _build_filter_config(filter_config: ScannerFilterConfig | dict[str, Any] | None) -> ScannerFilterConfig:
        if filter_config is None:
            return ScannerFilterConfig()
        if isinstance(filter_config, ScannerFilterConfig):
            return filter_config
        if isinstance(filter_config, dict):
            return replace(ScannerFilterConfig(), **filter_config)
        raise TypeError("filter_config must be None, ScannerFilterConfig, or dict")

    @staticmethod
    def _empty_result() -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "code",
                "name",
                "total_score",
                "triggered_strategies",
                "reasons",
                "risks",
                "close",
                "pct_chg",
                "amount",
                "turnover",
            ]
        )


def scan_stocks(
    stock_list: pd.DataFrame,
    data_provider: Any,
    strategies: Iterable[BaseStrategy],
    start_date,
    end_date,
    filter_config: ScannerFilterConfig | dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> pd.DataFrame:
    """Convenience function for one-off batch scans."""
    scanner = StockScanner(
        stock_list=stock_list,
        data_provider=data_provider,
        strategies=strategies,
        start_date=start_date,
        end_date=end_date,
        filter_config=filter_config,
        progress_callback=progress_callback,
    )
    return scanner.scan()
