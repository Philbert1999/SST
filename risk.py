"""Risk labels and observation suggestions for short-term stock candidates.

This module does not make trading decisions and does not place orders. It only
adds risk tags and observation suggestions to strategy signal results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

try:
    from config import APP_CONFIG, RiskConfig
except ImportError:
    from .config import APP_CONFIG, RiskConfig


@dataclass(frozen=True)
class RiskItem:
    tag: str
    reason: str
    suggestion: str
    severity: int

    def label(self) -> str:
        return f"{self.tag}：{self.reason}"


def analyze_risk(
    df: pd.DataFrame,
    stock_info: dict[str, Any] | None = None,
    signal_result: dict[str, Any] | None = None,
    config: RiskConfig | None = None,
) -> dict[str, Any]:
    """Analyze short-term observation risks for one stock.

    Args:
        df: Single-stock daily data with date/open/high/low/close/volume/amount/pct_chg/turnover.
        stock_info: Stock metadata such as code/name/sector/market.
        signal_result: Strategy signal result. It is accepted for integration and future rule expansion.
        config: Optional risk thresholds.

    Returns:
        {
            "risk_level": "低/中/高",
            "risk_tags": [clear risk reasons],
            "suggestions": [observation suggestions]
        }
    """
    cfg = config or APP_CONFIG.risk
    stock_info = stock_info or {}
    signal_result = signal_result or {}

    data = _normalize_daily_data(df)
    if data.empty:
        return {
            "risk_level": "高",
            "risk_tags": ["数据风险：日线数据为空，无法判断价格、成交量和换手风险。"],
            "suggestions": ["先检查数据源是否可用，不要基于缺失数据做短线判断。"],
        }

    risks: list[RiskItem] = []
    latest = data.iloc[-1]

    _check_recent_gain(data, cfg, risks)
    _check_today_pct_chg(latest, cfg, risks)
    _check_extreme_volume(data, cfg, risks)
    _check_ma5_bias(data, cfg, risks)
    _check_high_turnover(latest, cfg, risks)
    _check_consecutive_up_days(data, cfg, risks)
    _check_long_upper_shadow(latest, cfg, risks)
    _check_low_amount(latest, cfg, risks)

    if not risks:
        name = stock_info.get("name") or stock_info.get("code") or "该股票"
        strategy = signal_result.get("strategy") or signal_result.get("triggered_strategies") or "当前策略"
        return {
            "risk_level": "低",
            "risk_tags": [],
            "suggestions": [f"{name} 暂未触发主要短线风险标签，可继续结合 {strategy} 的信号原因观察。"],
        }

    severity_score = sum(item.severity for item in risks)
    risk_level = _risk_level(severity_score, cfg)
    suggestions = list(dict.fromkeys(item.suggestion for item in risks))

    return {
        "risk_level": risk_level,
        "risk_tags": [item.label() for item in risks],
        "suggestions": suggestions,
    }


def _normalize_daily_data(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    data = df.copy()
    for column in columns:
        if column not in data.columns:
            data[column] = pd.NA
    data = data[columns].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for column in columns:
        if column != "date":
            data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)


def _check_recent_gain(data: pd.DataFrame, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    required_rows = cfg.recent_gain_window + 1
    if len(data) < required_rows:
        return

    latest_close = data.iloc[-1]["close"]
    base_close = data.iloc[-required_rows]["close"]
    if pd.isna(base_close) or base_close <= 0:
        return

    gain_pct = (latest_close / base_close - 1) * 100
    if gain_pct > cfg.high_recent_gain_pct:
        risks.append(
            RiskItem(
                tag="高位风险",
                reason=f"最近 {cfg.recent_gain_window} 日涨幅约 {gain_pct:.1f}%，超过 {cfg.high_recent_gain_pct:.1f}%。",
                suggestion="短期涨幅已经较大，观察是否出现放量滞涨、跌破短期均线或板块退潮。",
                severity=3,
            )
        )


def _check_today_pct_chg(latest: pd.Series, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    pct_chg = latest.get("pct_chg")
    if pd.notna(pct_chg) and pct_chg > cfg.chase_high_pct_chg:
        risks.append(
            RiskItem(
                tag="追高风险",
                reason=f"今日涨幅 {pct_chg:.1f}%，超过 {cfg.chase_high_pct_chg:.1f}%。",
                suggestion="避免只因单日大涨追入，优先观察次日承接、成交量和回踩表现。",
                severity=2,
            )
        )


def _check_extreme_volume(data: pd.DataFrame, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    required_rows = cfg.extreme_volume_avg_days + 1
    if len(data) < required_rows:
        return

    latest_volume = data.iloc[-1]["volume"]
    avg_volume = data.iloc[-required_rows:-1]["volume"].mean()
    if pd.isna(avg_volume) or avg_volume <= 0:
        return

    volume_ratio = latest_volume / avg_volume
    if volume_ratio > cfg.extreme_volume_ratio:
        risks.append(
            RiskItem(
                tag="分歧风险",
                reason=f"今日成交量约为过去 {cfg.extreme_volume_avg_days} 日均量的 {volume_ratio:.2f} 倍，放量过快。",
                suggestion="极端放量常伴随分歧加大，观察收盘位置和次日是否继续放量承接。",
                severity=2,
            )
        )


def _check_ma5_bias(data: pd.DataFrame, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    if len(data) < 5:
        return

    latest_close = data.iloc[-1]["close"]
    ma5 = data["close"].rolling(5, min_periods=5).mean().iloc[-1]
    if pd.isna(ma5) or ma5 <= 0:
        return

    bias_pct = (latest_close / ma5 - 1) * 100
    if bias_pct > cfg.ma5_bias_threshold_pct:
        risks.append(
            RiskItem(
                tag="乖离风险",
                reason=f"收盘价高于 MA5 约 {bias_pct:.1f}%，超过 {cfg.ma5_bias_threshold_pct:.1f}%。",
                suggestion="短线乖离较大时，观察是否需要等待回踩 MA5 或横盘消化。",
                severity=2,
            )
        )


def _check_high_turnover(latest: pd.Series, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    turnover = latest.get("turnover")
    if pd.notna(turnover) and turnover > cfg.high_turnover_threshold:
        risks.append(
            RiskItem(
                tag="筹码不稳定",
                reason=f"今日换手率 {turnover:.1f}%，超过 {cfg.high_turnover_threshold:.1f}%。",
                suggestion="高换手说明筹码交换剧烈，观察是否出现冲高回落或次日低开。",
                severity=2,
            )
        )


def _check_consecutive_up_days(data: pd.DataFrame, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    up_days = 0
    for pct_chg in reversed(data["pct_chg"].dropna().tolist()):
        if pct_chg > 0:
            up_days += 1
        else:
            break

    if up_days >= cfg.consecutive_up_days_threshold:
        risks.append(
            RiskItem(
                tag="回调风险",
                reason=f"最近已连续上涨 {up_days} 天，达到 {cfg.consecutive_up_days_threshold} 天阈值。",
                suggestion="连续上涨后更容易出现短线获利盘，观察是否缩量横盘或跌破前一日低点。",
                severity=2,
            )
        )


def _check_long_upper_shadow(latest: pd.Series, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    high = latest.get("high")
    low = latest.get("low")
    close = latest.get("close")
    open_price = latest.get("open")
    if any(pd.isna(value) for value in [high, low, close, open_price]) or high <= low:
        return

    upper_shadow_ratio = (high - max(open_price, close)) / (high - low)
    if upper_shadow_ratio > cfg.long_upper_shadow_ratio:
        risks.append(
            RiskItem(
                tag="冲高回落",
                reason=f"今日上影线占振幅约 {upper_shadow_ratio:.0%}，超过 {cfg.long_upper_shadow_ratio:.0%}。",
                suggestion="长上影线说明上方抛压较明显，观察次日能否收复上影线高点。",
                severity=2,
            )
        )


def _check_low_amount(latest: pd.Series, cfg: RiskConfig, risks: list[RiskItem]) -> None:
    amount = latest.get("amount")
    if pd.notna(amount) and amount < cfg.low_amount_threshold:
        risks.append(
            RiskItem(
                tag="流动性风险",
                reason=f"今日成交额约 {amount / 100_000_000:.2f} 亿元，低于 {cfg.low_amount_threshold / 100_000_000:.2f} 亿元。",
                suggestion="成交额过低时买卖冲击成本可能较高，观察流动性是否持续改善。",
                severity=2,
            )
        )


def _risk_level(severity_score: int, cfg: RiskConfig) -> str:
    if severity_score >= cfg.high_risk_score:
        return "高"
    if severity_score >= cfg.medium_risk_score:
        return "中"
    return "低"
