"""Concrete short-term A-share strategies.

All "past N day" statistics intentionally exclude today's bar to avoid
future-function style leakage inside a same-day signal.
"""

from __future__ import annotations

import pandas as pd

from .base import BaseStrategy, EvaluationContext
from .config import BreakoutConfig, PullbackConfig, StrengthScoreConfig


class VolumeBreakoutStrategy(BaseStrategy):
    """放量突破策略."""

    name = "volume_breakout"
    display_name = "放量突破策略"

    def __init__(self, config: BreakoutConfig | None = None) -> None:
        super().__init__(config or BreakoutConfig())

    def _evaluate(self, context: EvaluationContext) -> dict:
        cfg: BreakoutConfig = self.config
        df = context.df
        stock_info = context.stock_info
        required_rows = max(cfg.breakout_days + 1, cfg.volume_avg_days + 1, cfg.ma_slow)
        if len(df) < required_rows:
            return self._insufficient_data(stock_info, required_rows, len(df))

        enriched = df.copy()
        enriched["ma_fast"] = self._ma(enriched, cfg.ma_fast)
        enriched["ma_slow"] = self._ma(enriched, cfg.ma_slow)

        today = enriched.iloc[-1]
        past_volume = enriched.iloc[-cfg.volume_avg_days - 1 : -1]["volume"]
        past_close_high = enriched.iloc[-cfg.breakout_days - 1 : -1]["close"].max()
        avg_volume = past_volume.mean()
        volume_ratio = today["volume"] / avg_volume if avg_volume > 0 else 0
        price_position = self._price_position_in_range(today["low"], today["high"], today["close"])

        checks = [
            (cfg.min_pct_chg <= today["pct_chg"] <= cfg.max_pct_chg, f"今日涨幅 {today['pct_chg']:.2f}% 位于 {cfg.min_pct_chg}% 到 {cfg.max_pct_chg}% 之间。"),
            (volume_ratio > cfg.volume_ratio_threshold, f"今日量比过去 {cfg.volume_avg_days} 日均量为 {volume_ratio:.2f}，超过 {cfg.volume_ratio_threshold}。"),
            (today["close"] > past_close_high, f"今日收盘价 {today['close']:.2f} 突破过去 {cfg.breakout_days} 日最高收盘价 {past_close_high:.2f}。"),
            (today["ma_fast"] > today["ma_slow"], f"MA{cfg.ma_fast} > MA{cfg.ma_slow}，短期均线保持多头。"),
            (price_position >= cfg.amplitude_upper_position, f"收盘价位于当日振幅上方区间，位置比例 {price_position:.2f}。"),
        ]

        passed_reasons = [reason for ok, reason in checks if ok]
        failed_reasons = [f"未满足：{reason}" for ok, reason in checks if not ok]
        signal = len(failed_reasons) == 0
        score = len(passed_reasons) / len(checks) * 100
        risks = [
            "突破后若快速跌回过去高点下方，可能是假突破。",
            "放量突破策略不代表买入结论，只用于候选股筛选。",
        ]
        return self._result(stock_info, signal, score, passed_reasons + failed_reasons, risks)


class StrongPullbackStrategy(BaseStrategy):
    """强势回踩策略."""

    name = "strong_pullback"
    display_name = "强势回踩策略"

    def __init__(self, config: PullbackConfig | None = None) -> None:
        super().__init__(config or PullbackConfig())

    def _evaluate(self, context: EvaluationContext) -> dict:
        cfg: PullbackConfig = self.config
        df = context.df
        stock_info = context.stock_info
        required_rows = max(cfg.recent_days + 1, cfg.ma_mid)
        if len(df) < required_rows:
            return self._insufficient_data(stock_info, required_rows, len(df))

        enriched = df.copy()
        enriched["ma_short"] = self._ma(enriched, cfg.ma_short)
        enriched["ma_mid"] = self._ma(enriched, cfg.ma_mid)

        today = enriched.iloc[-1]
        yesterday = enriched.iloc[-2]
        base_close = enriched.iloc[-cfg.recent_days - 1]["close"]
        recent_gain = (today["close"] / base_close - 1) * 100 if base_close > 0 else 0

        near_ma_short = self._pct_distance(today["low"], today["ma_short"]) < cfg.ma_near_tolerance_pct
        near_ma_mid = self._pct_distance(today["low"], today["ma_mid"]) < cfg.ma_near_tolerance_pct
        close_above_short = today["close"] >= today["ma_short"]
        close_above_mid = today["close"] >= today["ma_mid"]

        checks = [
            (recent_gain > cfg.min_recent_gain_pct, f"最近 {cfg.recent_days} 日涨幅 {recent_gain:.2f}%，大于 {cfg.min_recent_gain_pct}%。"),
            (near_ma_short or near_ma_mid, f"今日最低价接近 MA{cfg.ma_short} 或 MA{cfg.ma_mid}，误差小于 {cfg.ma_near_tolerance_pct}%。"),
            (today["volume"] < yesterday["volume"], "今日成交量小于昨日成交量，呈现缩量回踩。"),
            (close_above_short or close_above_mid, f"今日收盘价重新站上 MA{cfg.ma_short} 或 MA{cfg.ma_mid}。"),
            (today["pct_chg"] >= cfg.max_drop_pct, f"今日涨跌幅 {today['pct_chg']:.2f}%，未低于 {cfg.max_drop_pct}%。"),
        ]

        passed_reasons = [reason for ok, reason in checks if ok]
        failed_reasons = [f"未满足：{reason}" for ok, reason in checks if not ok]
        signal = len(failed_reasons) == 0
        score = len(passed_reasons) / len(checks) * 100
        risks = [
            "强势回踩依赖原趋势延续，若跌破关键均线需重新评估。",
            "缩量不一定代表抛压完全释放，仍需结合板块环境观察。",
        ]
        return self._result(stock_info, signal, score, passed_reasons + failed_reasons, risks)


class StrengthScoreStrategy(BaseStrategy):
    """强度打分策略."""

    name = "strength_score"
    display_name = "强度打分策略"

    def __init__(self, config: StrengthScoreConfig | None = None) -> None:
        super().__init__(config or StrengthScoreConfig())

    def _evaluate(self, context: EvaluationContext) -> dict:
        cfg: StrengthScoreConfig = self.config
        df = context.df
        stock_info = context.stock_info
        required_rows = max(cfg.ma_long, cfg.volume_avg_days + 1)
        if len(df) < required_rows:
            return self._insufficient_data(stock_info, required_rows, len(df))

        enriched = df.copy()
        enriched["ma_short"] = self._ma(enriched, cfg.ma_short)
        enriched["ma_mid"] = self._ma(enriched, cfg.ma_mid)
        enriched["ma_long"] = self._ma(enriched, cfg.ma_long)

        today = enriched.iloc[-1]
        past_volume = enriched.iloc[-cfg.volume_avg_days - 1 : -1]["volume"]
        avg_volume = past_volume.mean()
        volume_ratio = today["volume"] / avg_volume if avg_volume > 0 else 0
        price_position = self._price_position_in_range(today["low"], today["high"], today["close"])

        score = 0
        reasons: list[str] = []

        if cfg.pct_chg_min <= today["pct_chg"] <= cfg.pct_chg_max:
            score += cfg.pct_chg_score
            reasons.append(f"今日涨幅 {today['pct_chg']:.2f}% 位于 {cfg.pct_chg_min}% 到 {cfg.pct_chg_max}% 之间，加 {cfg.pct_chg_score} 分。")
        else:
            reasons.append(f"未加分：今日涨幅 {today['pct_chg']:.2f}% 不在目标区间。")

        if volume_ratio > cfg.volume_ratio_threshold:
            score += cfg.volume_ratio_score
            reasons.append(f"今日量比 {volume_ratio:.2f}，大于 {cfg.volume_ratio_threshold}，加 {cfg.volume_ratio_score} 分。")
        else:
            reasons.append(f"未加分：今日量比 {volume_ratio:.2f} 不足。")

        if price_position >= cfg.close_high_position:
            score += cfg.close_high_score
            reasons.append(f"收盘价接近最高价，区间位置 {price_position:.2f}，加 {cfg.close_high_score} 分。")
        else:
            reasons.append(f"未加分：收盘价区间位置 {price_position:.2f}，未接近最高价。")

        if today["ma_short"] > today["ma_mid"] > today["ma_long"]:
            score += cfg.ma_alignment_score
            reasons.append(f"MA{cfg.ma_short} > MA{cfg.ma_mid} > MA{cfg.ma_long}，加 {cfg.ma_alignment_score} 分。")
        else:
            reasons.append(f"未加分：均线未形成 MA{cfg.ma_short} > MA{cfg.ma_mid} > MA{cfg.ma_long}。")

        if today["amount"] > cfg.amount_threshold:
            score += cfg.amount_score
            reasons.append(f"成交额 {today['amount']:.0f} 元，大于 {cfg.amount_threshold:.0f} 元，加 {cfg.amount_score} 分。")
        else:
            reasons.append("未加分：成交额不足 3 亿。")

        if cfg.turnover_min <= today["turnover"] <= cfg.turnover_max:
            score += cfg.turnover_score
            reasons.append(f"换手率 {today['turnover']:.2f}% 位于 {cfg.turnover_min}% 到 {cfg.turnover_max}% 之间，加 {cfg.turnover_score} 分。")
        else:
            reasons.append(f"未加分：换手率 {today['turnover']:.2f}% 不在目标区间。")

        signal = score > cfg.signal_threshold
        if not signal:
            reasons.append(f"最终得分 {score}，未超过 {cfg.signal_threshold} 分，signal=False。")
        else:
            reasons.append(f"最终得分 {score}，超过 {cfg.signal_threshold} 分，signal=True。")

        risks = [
            "强度打分只衡量短线形态和流动性，不代表确定性收益。",
            "高分股票若处于情绪退潮期，仍可能快速回撤。",
        ]
        return self._result(stock_info, signal, score, reasons, risks)
