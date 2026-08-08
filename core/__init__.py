from core.models import (
    Signal,
    OrderSide,
    StrategyConfig,
    RiskConfig,
    Position,
    PendingEntry,
    StrategyAlert,
    BaseSideState,
    DayState,
)
from core.broker import BrokerInterface, ConsoleBroker, OpenAlgoBroker, HistoricalReplayBroker
from core.indicators import compute_rsi, add_indicators

__all__ = [
    "Signal",
    "OrderSide",
    "StrategyConfig",
    "RiskConfig",
    "Position",
    "PendingEntry",
    "StrategyAlert",
    "BaseSideState",
    "DayState",
    "BrokerInterface",
    "ConsoleBroker",
    "OpenAlgoBroker",
    "HistoricalReplayBroker",
    "compute_rsi",
    "add_indicators",
    "BaseStrategyEngine",
    "LiveFeedRunner",
    "run_historical_replay",
]


def __getattr__(name):
    if name == "BaseStrategyEngine":
        from core.engine import BaseStrategyEngine
        return BaseStrategyEngine
    if name == "LiveFeedRunner":
        from core.runner import LiveFeedRunner
        return LiveFeedRunner
    if name == "run_historical_replay":
        from core.runner import run_historical_replay
        return run_historical_replay
    raise AttributeError(f"module 'core' has no attribute {name!r}")
