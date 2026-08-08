"""Comprehensive tests for core/engine.py BaseStrategyEngine."""


class StubSignalProvider:
    """Minimal signal provider for engine-level tests."""

    def create_side_state(self):
        return None

    def update_state(self, side_state, row, prev_row):
        pass

    def generate_signal(self, side, side_state, row, prev_row):
        from core.models import Signal
        return Signal.NONE
