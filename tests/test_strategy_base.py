"""Tests for default methods in strategies.base.SignalProvider."""

import pandas as pd

from core.models import BaseSideState, Signal, StrategyConfig
from strategies.base import SignalProvider


class DummyProvider(SignalProvider):
    def create_side_state(self) -> BaseSideState:
        return BaseSideState()

    def update_state(self, side_state: BaseSideState, row: pd.Series, prev_row):
        pass

    def generate_signal(self, side: str, side_state: BaseSideState, row: pd.Series, prev_row):
        return Signal.NONE

    def compute_risk_points(self, side_state: BaseSideState, row: pd.Series):
        return 1.0

    def compute_entry_lots(self, row: pd.Series, cfg: StrategyConfig) -> int:
        return 1

    def compute_stop_level(self, side_state: BaseSideState, row: pd.Series) -> float:
        return 0.0

    def reset_after_entry(self, side_state: BaseSideState) -> None:
        pass


def test_default_optional_methods_return_empty_values():
    provider = DummyProvider()
    row = pd.Series({"close": 1.0})
    side_state = provider.create_side_state()
    assert provider.format_setup_status(side_state) == ""
    assert provider.diagnose_no_signal("CE", side_state, row, None) is None
