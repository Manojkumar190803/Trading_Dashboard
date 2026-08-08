"""Tests for core/__init__.py lazy-loading and re-export mechanism."""

import pytest


class TestCoreInitLazyLoading:
    """Verify the __getattr__ fallback works correctly."""

    def test_lazy_import_broker(self):
        from core import broker
        assert broker is not None

    def test_lazy_import_engine(self):
        from core import engine
        assert engine is not None

    def test_lazy_import_indicators(self):
        from core import indicators
        assert indicators is not None

    def test_lazy_import_models(self):
        from core import models
        assert models is not None

    def test_lazy_import_runner(self):
        from core import runner
        assert runner is not None


class TestCoreInitDirectImports:
    """Verify that direct imports of known names work."""

    def test_models_import(self):
        from core.models import (
            StrategyConfig, RiskConfig, Signal, BaseSideState, Position,
        )
        assert StrategyConfig is not None
        assert RiskConfig is not None
        assert Signal is not None
        assert BaseSideState is not None
        assert Position is not None

    def test_broker_import(self):
        from core.broker import ConsoleBroker
        assert ConsoleBroker is not None


def test_core_getattr_exports_and_invalid_name():
    import core

    assert core.__getattr__("BaseStrategyEngine") is not None
    assert core.__getattr__("LiveFeedRunner") is not None
    assert core.__getattr__("run_historical_replay") is not None

    with pytest.raises(AttributeError):
        core.__getattr__("DOES_NOT_EXIST")