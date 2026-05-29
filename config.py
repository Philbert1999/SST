"""Project-wide configuration for the A-share short-term screener.

All user-facing defaults, stock filters, and strategy parameters live here.
The dataclasses are intentionally small and explicit so beginners can edit
values without hunting through the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
EXPORT_DIR = BASE_DIR / "exports"
SNAPSHOT_DIR = BASE_DIR / "snapshots"


@dataclass(frozen=True)
class FilterConfig:
    """Basic stock-pool filters."""

    min_price: float = 3.0
    min_amount: float = 300_000_000
    exclude_st: bool = True
    exclude_new_stock_days: int = 60
    max_20d_gain: float = 40.0
    exclude_delisting_risk: bool = True
    max_price: float = 200.0
    exclude_star_market: bool = True
    exclude_beijing_exchange: bool = True

    # Compatibility aliases used by older modules.
    @property
    def min_turnover_amount(self) -> float:
        return self.min_amount

    @property
    def min_listing_days(self) -> int:
        return self.exclude_new_stock_days

    @property
    def max_recent_gain_pct(self) -> float:
        return self.max_20d_gain


@dataclass(frozen=True)
class BreakoutStrategyConfig:
    """Volume breakout strategy parameters."""

    min_pct_chg: float = 2.0
    max_pct_chg: float = 7.0
    volume_ratio_threshold: float = 1.5
    breakout_window: int = 20
    close_position_threshold: float = 0.7
    volume_avg_days: int = 5
    ma_fast: int = 5
    ma_slow: int = 10

    # Compatibility aliases used by strategy_framework.strategies.
    @property
    def breakout_days(self) -> int:
        return self.breakout_window

    @property
    def amplitude_upper_position(self) -> float:
        return self.close_position_threshold


@dataclass(frozen=True)
class PullbackStrategyConfig:
    """Strong pullback strategy parameters."""

    recent_gain_window: int = 10
    recent_gain_threshold: float = 8.0
    ma_touch_tolerance: float = 0.02
    max_drop_pct: float = -3.0
    ma_short: int = 5
    ma_mid: int = 10

    # Compatibility aliases used by strategy_framework.strategies.
    @property
    def recent_days(self) -> int:
        return self.recent_gain_window

    @property
    def min_recent_gain_pct(self) -> float:
        return self.recent_gain_threshold

    @property
    def ma_near_tolerance_pct(self) -> float:
        return self.ma_touch_tolerance * 100


@dataclass(frozen=True)
class StrengthScoreConfig:
    """Strength scoring strategy parameters."""

    signal_score_threshold: int = 70
    min_turnover: float = 3.0
    max_turnover: float = 20.0
    pct_chg_min: float = 3.0
    pct_chg_max: float = 8.0
    pct_chg_score: int = 25
    volume_avg_days: int = 5
    volume_ratio_threshold: float = 1.5
    volume_ratio_score: int = 25
    close_high_position: float = 0.8
    close_high_score: int = 20
    ma_short: int = 5
    ma_mid: int = 10
    ma_long: int = 20
    ma_alignment_score: int = 20
    amount_threshold: float = 300_000_000
    amount_score: int = 10
    turnover_score: int = 10

    # Compatibility aliases used by strategy_framework.strategies.
    @property
    def signal_threshold(self) -> int:
        return self.signal_score_threshold

    @property
    def turnover_min(self) -> float:
        return self.min_turnover

    @property
    def turnover_max(self) -> float:
        return self.max_turnover


@dataclass(frozen=True)
class SectorHeatConfig:
    """Sector heat parameters."""

    top_n: int = 20


@dataclass(frozen=True)
class ScannerConfig:
    """Batch scanner and cache parameters."""

    cache_ttl_seconds: int = 60 * 10
    daily_cache_ttl_seconds: int = 60 * 60 * 6
    overheat_days: int = 20
    max_workers: int = 8
    history_days: int = 180
    top_n: int = 100


@dataclass(frozen=True)
class UIConfig:
    """Streamlit default values."""

    default_history_days: int = 180
    default_min_amount_yi: float = 3.0
    default_min_price: float = 3.0
    default_max_price: float = 200.0
    default_exclude_st: bool = True
    default_exclude_new_stock: bool = True
    default_exclude_star_market: bool = True


@dataclass(frozen=True)
class RiskConfig:
    """Risk label thresholds for short-term observation."""

    recent_gain_window: int = 20
    high_recent_gain_pct: float = 40.0
    chase_high_pct_chg: float = 7.0
    extreme_volume_avg_days: int = 5
    extreme_volume_ratio: float = 3.0
    ma5_bias_threshold_pct: float = 8.0
    high_turnover_threshold: float = 20.0
    consecutive_up_days_threshold: int = 5
    long_upper_shadow_ratio: float = 0.45
    low_amount_threshold: float = 300_000_000
    medium_risk_score: int = 3
    high_risk_score: int = 6


@dataclass(frozen=True)
class LegacyStrategyConfig:
    """Compatibility view for older strategy modules."""

    breakout_window: int
    breakout_volume_ratio: float
    pullback_ma_window: int
    pullback_max_distance_pct: float
    strength_lookback: int
    sector_top_n: int


@dataclass(frozen=True)
class AppConfig:
    filter: FilterConfig = field(default_factory=FilterConfig)
    breakout: BreakoutStrategyConfig = field(default_factory=BreakoutStrategyConfig)
    pullback: PullbackStrategyConfig = field(default_factory=PullbackStrategyConfig)
    strength: StrengthScoreConfig = field(default_factory=StrengthScoreConfig)
    sector_heat: SectorHeatConfig = field(default_factory=SectorHeatConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @property
    def strategy(self) -> LegacyStrategyConfig:
        return LegacyStrategyConfig(
            breakout_window=self.breakout.breakout_window,
            breakout_volume_ratio=self.breakout.volume_ratio_threshold,
            pullback_ma_window=self.pullback.ma_short,
            pullback_max_distance_pct=self.pullback.ma_near_tolerance_pct,
            strength_lookback=self.strength.ma_long,
            sector_top_n=self.sector_heat.top_n,
        )


APP_CONFIG = AppConfig()

# Backward-compatible name used by older modules.
DEFAULT_CONFIG = APP_CONFIG


DISPLAY_COLUMNS = [
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
