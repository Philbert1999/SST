"""AKShare data provider for A-share short-term screening."""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

try:
    from config import DEFAULT_CONFIG
    from data.cache import FileCache
    from data.data_provider import DataProvider
except ImportError:
    from ..config import DEFAULT_CONFIG
    from .cache import FileCache
    from .data_provider import DataProvider


logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")


DAILY_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]


class AkshareProvider(DataProvider):
    """AKShare implementation with cache, fallback endpoints, and normalized fields."""

    def __init__(
        self,
        cache: FileCache | None = None,
        cache_ttl_seconds: int | None = None,
        daily_cache_ttl_seconds: int | None = None,
        adjust: str = "qfq",
    ) -> None:
        self.cache = cache or FileCache()
        self.cache_ttl_seconds = cache_ttl_seconds or DEFAULT_CONFIG.scanner.cache_ttl_seconds
        self.daily_cache_ttl_seconds = daily_cache_ttl_seconds or DEFAULT_CONFIG.scanner.daily_cache_ttl_seconds
        self.adjust = adjust
        self.errors: list[dict[str, Any]] = []
        self._prefer_sina_daily = False

    def get_stock_list(self) -> pd.DataFrame:
        cache_key = "akshare_stock_list"
        cached = self.cache.get(cache_key, self.cache_ttl_seconds)
        if cached is not None:
            logger.info("Loaded stock list from cache: %s rows", len(cached))
            return cached.copy()

        quotes = self.get_realtime_quotes()
        if not quotes.empty:
            stock_list = quotes[["code", "name", "market", "is_st", "listing_date"]].copy()
            stock_list = stock_list.drop_duplicates(subset=["code"]).sort_values("code").reset_index(drop=True)
            self.cache.set(cache_key, stock_list)
            logger.info("Built stock list from realtime quotes: %s rows", len(stock_list))
            return stock_list

        stock_list = self._get_stock_list_fallback()
        self.cache.set(cache_key, stock_list)
        return stock_list

    def get_daily_data(self, code: str, start_date, end_date, force_refresh: bool = False) -> pd.DataFrame:
        code = self._normalize_code(code)
        start = self._normalize_date(start_date)
        end = self._normalize_date(end_date)
        cache_key = f"akshare_daily_{code}_{start}_{end}_{self.adjust}"
        cached = None if force_refresh else self.cache.get(cache_key, self.daily_cache_ttl_seconds)
        if cached is not None:
            logger.info("Loaded daily data from cache: %s %s rows", code, len(cached))
            return cached.copy()

        try:
            import akshare as ak

            if self._prefer_sina_daily:
                raw = self._fetch_sina_daily(ak, code, start, end)
            else:
                try:
                    raw = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start,
                        end_date=end,
                        adjust=self.adjust,
                    )
                except Exception as primary_exc:
                    logger.warning("Eastmoney daily endpoint failed for %s, switching to Sina fallback: %s", code, primary_exc)
                    self._prefer_sina_daily = True
                    raw = self._fetch_sina_daily(ak, code, start, end)

            df = self._standardize_daily_data(raw)
            self.cache.set(cache_key, df)
            logger.info("Fetched daily data: %s %s rows", code, len(df))
            return df
        except Exception as exc:
            logger.error("Failed to fetch daily data for %s: %s", code, exc)
            self.errors.append({"scope": "daily", "code": code, "error": str(exc)})
            return pd.DataFrame(columns=DAILY_COLUMNS)

    def get_realtime_quotes(self) -> pd.DataFrame:
        cache_key = "akshare_realtime_quotes"
        cached = self.cache.get(cache_key, self.cache_ttl_seconds)
        if cached is not None:
            logger.info("Loaded realtime quotes from cache: %s rows", len(cached))
            return cached.copy()

        try:
            import akshare as ak

            raw = ak.stock_zh_a_spot_em()
            df = self._standardize_realtime_quotes(raw)
            self.cache.set(cache_key, df)
            logger.info("Fetched realtime quotes: %s rows", len(df))
            return df
        except Exception as exc:
            logger.error("Failed to fetch realtime quotes: %s", exc)
            self.errors.append({"scope": "realtime_quotes", "error": str(exc)})
            return self._empty_realtime_quotes()

    def get_sector_data(self) -> pd.DataFrame:
        cache_key = "akshare_sector_data"
        cached = self.cache.get(cache_key, self.cache_ttl_seconds)
        if cached is not None:
            logger.info("Loaded sector data from cache: %s rows", len(cached))
            return cached.copy()

        try:
            import akshare as ak

            raw = ak.stock_board_industry_name_em()
            df = self._standardize_sector_data(raw)
            self.cache.set(cache_key, df)
            logger.info("Fetched sector data: %s rows", len(df))
            return df
        except Exception as exc:
            logger.error("Failed to fetch sector data: %s", exc)
            self.errors.append({"scope": "sector_data", "error": str(exc)})
            return pd.DataFrame(columns=["sector", "pct_chg", "amount", "turnover", "up_count", "down_count", "leader", "leader_pct_chg", "sector_rank"])

    def get_stock_spot(self) -> pd.DataFrame:
        quotes = self.get_realtime_quotes()
        if quotes.empty:
            return quotes
        result = quotes.copy()
        result["latest_price"] = result["close"]
        result["pct_change"] = result["pct_chg"]
        result["turnover_amount"] = result["amount"]
        result["turnover_rate"] = result["turnover"]
        return result

    def get_daily_history(self, code: str, start_date: date | None = None, end_date: date | None = None, adjust: str | None = None) -> pd.DataFrame:
        original_adjust = self.adjust
        if adjust is not None:
            self.adjust = adjust
        try:
            start = start_date or (date.today() - timedelta(days=180))
            end = end_date or date.today()
            df = self.get_daily_data(code, start, end)
            if df.empty:
                return df
            result = df.copy()
            result["turnover_amount"] = result["amount"]
            result["pct_change"] = result["pct_chg"]
            result["turnover_rate"] = result["turnover"]
            return result
        finally:
            self.adjust = original_adjust

    def get_sector_rank(self) -> pd.DataFrame:
        df = self.get_sector_data()
        if df.empty:
            return df
        result = df.copy()
        result["pct_change"] = result["pct_chg"]
        result["turnover_rate"] = result["turnover"]
        return result

    def _get_stock_list_fallback(self) -> pd.DataFrame:
        try:
            import akshare as ak

            raw = ak.stock_info_a_code_name()
            df = raw.rename(columns={"\u4ee3\u7801": "code", "\u540d\u79f0": "name"})
            if "code" not in df.columns or "name" not in df.columns:
                return self._empty_stock_list()
            df = df[["code", "name"]].copy()
            df["code"] = df["code"].astype(str).str.zfill(6)
            df["name"] = df["name"].astype(str)
            df["market"] = df["code"].map(self._infer_market)
            df["is_st"] = df["name"].str.contains("ST|\\*ST", case=False, regex=True, na=False)
            df["listing_date"] = pd.NaT
            df = df[["code", "name", "market", "is_st", "listing_date"]]
            logger.info("Fetched stock list from fallback endpoint: %s rows", len(df))
            return df.drop_duplicates(subset=["code"]).sort_values("code").reset_index(drop=True)
        except Exception as exc:
            logger.error("Fallback stock list endpoint failed: %s", exc)
            self.errors.append({"scope": "stock_list_fallback", "error": str(exc)})
            return self._empty_stock_list()

    def _fetch_sina_daily(self, ak_module, code: str, start: str, end: str) -> pd.DataFrame:
        return ak_module.stock_zh_a_daily(
            symbol=self._ak_market_symbol(code),
            start_date=start,
            end_date=end,
            adjust=self.adjust,
        )

    def _standardize_daily_data(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame(columns=DAILY_COLUMNS)

        df = raw.rename(
            columns={
                "\u65e5\u671f": "date",
                "\u5f00\u76d8": "open",
                "\u6700\u9ad8": "high",
                "\u6700\u4f4e": "low",
                "\u6536\u76d8": "close",
                "\u6210\u4ea4\u91cf": "volume",
                "\u6210\u4ea4\u989d": "amount",
                "\u6da8\u8dcc\u5e45": "pct_chg",
                "\u6362\u624b\u7387": "turnover",
            }
        )
        for column in DAILY_COLUMNS:
            if column not in df.columns:
                df[column] = pd.NA

        df = df[DAILY_COLUMNS].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for column in DAILY_COLUMNS:
            if column != "date":
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if df["pct_chg"].isna().all() and len(df) > 1:
            df["pct_chg"] = df["close"].pct_change() * 100
        if df["turnover"].notna().any() and df["turnover"].max(skipna=True) <= 1:
            df["turnover"] = df["turnover"] * 100
        return df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)

    def _standardize_realtime_quotes(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return self._empty_realtime_quotes()

        df = raw.rename(
            columns={
                "\u4ee3\u7801": "code",
                "\u540d\u79f0": "name",
                "\u6700\u65b0\u4ef7": "close",
                "\u6da8\u8dcc\u5e45": "pct_chg",
                "\u6210\u4ea4\u91cf": "volume",
                "\u6210\u4ea4\u989d": "amount",
                "\u6700\u9ad8": "high",
                "\u6700\u4f4e": "low",
                "\u4eca\u5f00": "open",
                "\u6628\u6536": "pre_close",
                "\u91cf\u6bd4": "volume_ratio",
                "\u6362\u624b\u7387": "turnover",
                "\u884c\u4e1a": "sector",
                "\u4e0a\u5e02\u65f6\u95f4": "listing_date",
            }
        )
        defaults = {
            "code": "",
            "name": "",
            "market": "",
            "is_st": False,
            "listing_date": pd.NaT,
            "open": pd.NA,
            "high": pd.NA,
            "low": pd.NA,
            "close": pd.NA,
            "pre_close": pd.NA,
            "volume": pd.NA,
            "amount": pd.NA,
            "pct_chg": pd.NA,
            "turnover": pd.NA,
            "volume_ratio": pd.NA,
            "sector": "",
        }
        for column, default in defaults.items():
            if column not in df.columns:
                df[column] = default

        df["code"] = df["code"].astype(str).str.zfill(6)
        df["name"] = df["name"].astype(str)
        df["market"] = df["code"].map(self._infer_market)
        df["is_st"] = df["name"].str.contains("ST|\\*ST", case=False, regex=True, na=False)
        df["listing_date"] = pd.to_datetime(df["listing_date"], format="%Y%m%d", errors="coerce")
        for column in ["open", "high", "low", "close", "pre_close", "volume", "amount", "pct_chg", "turnover", "volume_ratio"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        return df[list(defaults)].drop_duplicates(subset=["code"]).reset_index(drop=True)

    def _standardize_sector_data(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.rename(
            columns={
                "\u677f\u5757\u540d\u79f0": "sector",
                "\u6da8\u8dcc\u5e45": "pct_chg",
                "\u6210\u4ea4\u989d": "amount",
                "\u6362\u624b\u7387": "turnover",
                "\u4e0a\u6da8\u5bb6\u6570": "up_count",
                "\u4e0b\u8dcc\u5bb6\u6570": "down_count",
                "\u9886\u6da8\u80a1\u7968": "leader",
                "\u9886\u6da8\u80a1\u7968-\u6da8\u8dcc\u5e45": "leader_pct_chg",
            }
        )
        defaults = {
            "sector": "",
            "pct_chg": pd.NA,
            "amount": pd.NA,
            "turnover": pd.NA,
            "up_count": pd.NA,
            "down_count": pd.NA,
            "leader": "",
            "leader_pct_chg": pd.NA,
        }
        for column, default in defaults.items():
            if column not in df.columns:
                df[column] = default
        for column in ["pct_chg", "amount", "turnover", "up_count", "down_count", "leader_pct_chg"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df = df[list(defaults)].sort_values("pct_chg", ascending=False, na_position="last").reset_index(drop=True)
        df["sector_rank"] = df.index + 1
        return df

    @staticmethod
    def _normalize_code(code: str) -> str:
        return str(code).strip().split(".")[0].zfill(6)

    @staticmethod
    def _normalize_date(value) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        text = str(value).replace("-", "").replace("/", "")
        if len(text) != 8 or not text.isdigit():
            raise ValueError(f"Invalid date: {value!r}; expected YYYYMMDD or YYYY-MM-DD")
        return text

    @staticmethod
    def _ak_market_symbol(code: str) -> str:
        market = AkshareProvider._infer_market(code).lower()
        if market in {"sh", "sz"}:
            return f"{market}{str(code).zfill(6)}"
        return str(code).zfill(6)

    @staticmethod
    def _infer_market(code: str) -> str:
        code = str(code).zfill(6)
        if code.startswith(("600", "601", "603", "605", "688", "689")):
            return "SH"
        if code.startswith(("000", "001", "002", "003", "300", "301")):
            return "SZ"
        if code.startswith(("430", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "920")):
            return "BJ"
        return "UNKNOWN"

    @staticmethod
    def _empty_stock_list() -> pd.DataFrame:
        return pd.DataFrame(columns=["code", "name", "market", "is_st", "listing_date"])

    @staticmethod
    def _empty_realtime_quotes() -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "code",
                "name",
                "market",
                "is_st",
                "listing_date",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
                "amount",
                "pct_chg",
                "turnover",
                "volume_ratio",
                "sector",
            ]
        )


def test_random_daily_data(sample_size: int = 5, days: int = 60) -> None:
    provider = AkshareProvider()
    stock_list = provider.get_stock_list()
    if stock_list.empty:
        logger.warning("No stock list available; cannot run daily data test.")
        return

    available = stock_list[~stock_list["is_st"].fillna(False)].copy()
    sampled = available.loc[random.sample(list(available.index), min(sample_size, len(available)))]
    end_date = date.today()
    start_date = end_date - timedelta(days=days * 2)
    for _, stock in sampled.iterrows():
        code = stock["code"]
        name = stock["name"]
        logger.info("Testing daily data: %s %s", code, name)
        df = provider.get_daily_data(code, start_date, end_date).tail(days)
        print(f"\n===== {code} {name} recent {days} days =====")
        print(df.to_string(index=False))


if __name__ == "__main__":
    test_random_daily_data()
