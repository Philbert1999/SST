from __future__ import annotations

import unittest
from dataclasses import replace

import pandas as pd

from config import APP_CONFIG
from risk import analyze_risk


def make_daily_data(
    periods: int = 30,
    start_close: float = 10.0,
    step: float = 0.05,
    pct_chg: float = 0.5,
    volume: float = 10_000_000,
    amount: float = 500_000_000,
    turnover: float = 5.0,
) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=periods, freq="B")
    closes = [start_close + i * step for i in range(periods)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [close * 0.99 for close in closes],
            "high": [close * 1.01 for close in closes],
            "low": [close * 0.98 for close in closes],
            "close": closes,
            "volume": [volume] * periods,
            "amount": [amount] * periods,
            "pct_chg": [pct_chg] * periods,
            "turnover": [turnover] * periods,
        }
    )


class RiskAnalyzeTest(unittest.TestCase):
    def test_low_risk_when_no_rule_triggered(self) -> None:
        df = make_daily_data(step=0.02, pct_chg=0.2)
        df["pct_chg"] = [0.2 if i % 2 == 0 else -0.1 for i in range(len(df))]
        result = analyze_risk(df, {"code": "000001", "name": "测试股"}, {"strategy": "测试策略"})

        self.assertEqual(result["risk_level"], "低")
        self.assertEqual(result["risk_tags"], [])
        self.assertTrue(result["suggestions"])

    def test_high_risk_when_multiple_rules_triggered(self) -> None:
        df = make_daily_data(start_close=10, step=0.35, pct_chg=1.0)
        df.loc[df.index[-1], ["open", "high", "low", "close"]] = [21.0, 25.0, 20.0, 21.2]
        df.loc[df.index[-1], "pct_chg"] = 9.0
        df.loc[df.index[-1], "volume"] = 80_000_000
        df.loc[df.index[-1], "turnover"] = 25.0
        df.loc[df.index[-1], "amount"] = 200_000_000

        result = analyze_risk(df, {"code": "000001", "name": "测试股"}, {"strategy": "强度打分"})
        joined_tags = "\n".join(result["risk_tags"])

        self.assertEqual(result["risk_level"], "高")
        self.assertIn("高位风险", joined_tags)
        self.assertIn("追高风险", joined_tags)
        self.assertIn("分歧风险", joined_tags)
        self.assertIn("筹码不稳定", joined_tags)
        self.assertIn("冲高回落", joined_tags)
        self.assertIn("流动性风险", joined_tags)

    def test_empty_data_is_high_data_risk(self) -> None:
        result = analyze_risk(pd.DataFrame(), {}, {})

        self.assertEqual(result["risk_level"], "高")
        self.assertIn("数据风险", result["risk_tags"][0])

    def test_configurable_today_gain_threshold(self) -> None:
        df = make_daily_data(pct_chg=0.3)
        df.loc[df.index[-1], "pct_chg"] = 5.0
        cfg = replace(APP_CONFIG.risk, chase_high_pct_chg=4.0)

        result = analyze_risk(df, {}, {}, cfg)
        joined_tags = "\n".join(result["risk_tags"])

        self.assertIn("追高风险", joined_tags)


if __name__ == "__main__":
    unittest.main()
