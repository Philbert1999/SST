from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import app


class AppTestCase(TestCase):
    def setUp(self):
        app.load_stock_list.clear()
        app.load_daily_data.clear()
        self.addCleanup(app.load_stock_list.clear)
        self.addCleanup(app.load_daily_data.clear)

    def test_failed_fetch_is_not_memoized(self):
        valid = pd.DataFrame({"code": ["000001"]})
        provider = Mock()
        provider.get_stock_list.side_effect = [pd.DataFrame(), valid]
        with self.assertRaises(RuntimeError):
            app.load_stock_list(provider, "test")
        self.assertEqual(len(app.load_stock_list(provider, "test")), 1)
        self.assertEqual(provider.get_stock_list.call_count, 2)

    def test_sidebar_and_refresh_failure_do_not_crash(self):
        provider = Mock()
        provider.get_stock_list.return_value = pd.DataFrame()
        with patch.object(app, "get_data_provider", return_value=provider):
            page = AppTest.from_string("from app import main\nmain()").run()
            self.assertFalse(page.exception)
            provider.get_stock_list.assert_not_called()
            next(b for b in page.button if b.label == "刷新股票列表 / 重试连接").click().run()
            self.assertFalse(page.exception)
            self.assertTrue(any("数据源仍不可用" in item.value for item in page.error))
            provider.get_stock_list.assert_called_once_with(force_refresh=True)

    def test_failed_new_scan_preserves_results_and_their_dates(self):
        previous = pd.DataFrame({"code": ["000001"], "name": ["测试股"], "total_score": [70],
                                 "triggered_strategies": ["测试"], "reasons": ["测试"], "risks": [""],
                                 "close": [10], "pct_chg": [1], "amount": [500000000], "turnover": [2]})
        period = {"start_date": date(2026, 1, 1), "end_date": date(2026, 2, 1)}
        with patch.object(app, "get_data_provider", return_value=Mock()), \
             patch.object(app, "load_stock_list", side_effect=RuntimeError("offline")), \
             patch.object(app, "load_daily_data", side_effect=RuntimeError("offline")):
            page = AppTest.from_string("from app import main\nmain()").run()
            page.session_state["scan_results"] = previous
            page.session_state["last_scan_options"] = period
            next(b for b in page.button if b.label == "运行筛选").click().run()
            self.assertFalse(page.exception)
            self.assertTrue(page.session_state["scan_results"].equals(previous))
            self.assertEqual(page.session_state["last_scan_options"], period)
            self.assertTrue(any("上次筛选结果已保留" in item.value for item in page.error))
