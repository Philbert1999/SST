"""Strategy configuration aliases.

The canonical strategy parameters live in the project root `config.py`.
This module keeps the shorter names used by the strategy framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:
    from config import (
        APP_CONFIG,
        BreakoutStrategyConfig,
        PullbackStrategyConfig,
        StrengthScoreConfig,
    )
except ImportError:
    from ..config import (
        APP_CONFIG,
        BreakoutStrategyConfig,
        PullbackStrategyConfig,
        StrengthScoreConfig,
    )


BreakoutConfig = BreakoutStrategyConfig
PullbackConfig = PullbackStrategyConfig


@dataclass(frozen=True)
class StrategyFrameworkConfig:
    breakout: BreakoutConfig = field(default_factory=lambda: APP_CONFIG.breakout)
    pullback: PullbackConfig = field(default_factory=lambda: APP_CONFIG.pullback)
    strength_score: StrengthScoreConfig = field(default_factory=lambda: APP_CONFIG.strength)


DEFAULT_STRATEGY_CONFIG = StrategyFrameworkConfig()
