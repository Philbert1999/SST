from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd

from data.akshare_provider import AkshareProvider
from data.cache import FileCache
from performance import evaluate_snapshot, save_screening_snapshot
from strategy_framework.scanner import StockScanner


def bars():
    return pd.DataFrame({"date": ["2026-01-02", "2026-01-05"], "close": [10, 11],
                         "volume": [1000, 1200], "turnover": [.5, .8]})


class CacheTest(TestCase):
    def test_failed_write_preserves_previous_cache(self):
        with TemporaryDirectory() as folder:
            cache = FileCache(Path(folder))
            cache.set("daily", {"close": 10})
            with patch("data.cache.pickle.dump", side_effect=OSError("disk full")):
                cache.set("daily", {"close": 20})
            self.assertEqual(cache.get("daily", 60), {"close": 10})
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_bad_or_missing_file_is_a_cache_miss(self):
        with TemporaryDirectory() as folder:
            cache = FileCache(Path(folder))
            self.assertIsNone(cache.get("missing", 60))
            cache._path("bad").write_bytes(b"corrupt")
            self.assertIsNone(cache.get("bad", 60))


class ProviderTest(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.provider = AkshareProvider(cache=FileCache(Path(self.folder.name)))

    def test_empty_list_is_not_cached_and_next_call_can_recover(self):
        valid = pd.DataFrame({"code": ["000001"], "name": ["测试股"], "market": ["SZ"],
                              "is_st": [False], "listing_date": [pd.NaT]})
        with patch.object(self.provider, "get_realtime_quotes", return_value=valid.iloc[:0]), \
             patch.object(self.provider, "_get_stock_list_fallback", side_effect=[valid.iloc[:0], valid]) as fallback:
            self.assertTrue(self.provider.get_stock_list().empty)
            self.assertEqual(len(self.provider.get_stock_list()), 1)
            self.assertEqual(fallback.call_count, 2)

    def test_force_refresh_bypasses_successful_list_cache(self):
        valid = pd.DataFrame({"code": ["000001"], "name": ["旧"], "market": ["SZ"],
                              "is_st": [False], "listing_date": [pd.NaT]})
        self.provider.cache.set("akshare_stock_list", valid)
        fresh = valid.assign(name="新")
        with patch.object(self.provider, "get_realtime_quotes", return_value=fresh) as quotes:
            self.assertEqual(self.provider.get_stock_list(force_refresh=True).iloc[0]["name"], "新")
            quotes.assert_called_once_with(force_refresh=True)

    def test_empty_primary_daily_falls_back_without_sticky_empty_cache(self):
        fake = SimpleNamespace(stock_zh_a_hist=Mock(return_value=pd.DataFrame()),
                               stock_zh_a_daily=Mock(side_effect=[pd.DataFrame(), bars()]))
        with patch.dict("sys.modules", {"akshare": fake}):
            self.assertTrue(self.provider.get_daily_data("000001", "20260101", "20260106").empty)
            self.assertEqual(len(self.provider.get_daily_data("000001", "20260101", "20260106")), 2)
        self.assertEqual(fake.stock_zh_a_daily.call_count, 2)

    def test_turnover_units_depend_on_source_not_magnitude(self):
        primary = self.provider._standardize_daily_data(bars(), source="eastmoney")
        fallback = self.provider._standardize_daily_data(bars(), source="sina")
        self.assertEqual(primary.iloc[0]["turnover"], .5)
        self.assertEqual(fallback.iloc[0]["turnover"], 50)
        self.assertEqual(fallback.iloc[0]["volume"], 10)

    def test_provider_failure_is_visible_in_scanner_errors(self):
        class FailingProvider:
            errors = []
            def get_daily_data(self, *args):
                self.errors.append({"error": "connection lost"})
                return pd.DataFrame()
        scanner = StockScanner(pd.DataFrame({"code": ["000001"], "name": ["测试股"]}),
                               FailingProvider(), [], date(2026, 1, 1), date(2026, 1, 6))
        self.assertTrue(scanner.scan().empty)
        self.assertIn("connection lost", scanner.errors[0]["error"])


class SnapshotTest(TestCase):
    def test_same_timestamp_snapshots_do_not_overwrite(self):
        with TemporaryDirectory() as folder, patch("performance.SNAPSHOT_DIR", Path(folder)), \
             patch("performance.datetime") as clock:
            clock.now.return_value = datetime(2026, 1, 2, 12)
            first = save_screening_snapshot(pd.DataFrame({"code": ["000001"]}), "2026-01-02")
            second = save_screening_snapshot(pd.DataFrame({"code": ["000002"]}), "2026-01-02")
            self.assertNotEqual(first, second)
            self.assertEqual(len(list(Path(folder).glob("*.csv"))), 2)

    def test_failed_snapshot_does_not_leave_partial_csv(self):
        with TemporaryDirectory() as folder, patch("performance.SNAPSHOT_DIR", Path(folder)), \
             patch.object(pd.DataFrame, "to_csv", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                save_screening_snapshot(pd.DataFrame({"code": ["000001"]}), "2026-01-02")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_bad_date_only_fails_its_own_row(self):
        provider = SimpleNamespace(get_daily_data=lambda *args, **kwargs: bars())
        snapshot = pd.DataFrame({"code": ["000001", "000002"], "signal_date": ["bad", "2026-01-02"]})
        result = evaluate_snapshot(snapshot, provider, horizon=1)
        self.assertTrue(result.iloc[0]["eval_error"])
        self.assertEqual(result.iloc[1]["return_d1"], 10)
