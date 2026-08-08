"""Tests for BaseStrategyEngine initialization."""


class StubSignalProvider:
    """Minimal signal provider for engine-level tests."""

    def create_side_state(self):
        return None

    def update_state(self, side_state, row, prev_row):
        pass

    def generate_signal(self, side, side_state, row, prev_row):
        from core.models import Signal
        return Signal.NONE


class TestEngineInit:
    """Test BaseStrategyEngine initialization."""

    def test_init_with_all_params(self):
        from core.engine import BaseStrategyEngine
        from core.models import StrategyConfig, RiskConfig
        from core.broker import ConsoleBroker
        cfg = StrategyConfig(min_vwap_room_rr=1.5)
        risk = RiskConfig()
        broker = ConsoleBroker()
        engine = BaseStrategyEngine(
            cfg=cfg, risk=risk, broker=broker, signal_provider=StubSignalProvider(),
        )
        assert isinstance(engine, BaseStrategyEngine)

    def test_init_with_atm_locked(self):
        from core.engine import BaseStrategyEngine
        from core.models import StrategyConfig, RiskConfig
        from core.broker import ConsoleBroker
        cfg = StrategyConfig(min_vwap_room_rr=1.5)
        risk = RiskConfig()
        broker = ConsoleBroker()
        engine = BaseStrategyEngine(
            cfg=cfg, risk=risk, broker=broker, signal_provider=StubSignalProvider(),
        )
        engine.state.atm_locked = True
        assert engine.state.atm_locked is True

    def test_init_with_symbols(self):
        from core.engine import BaseStrategyEngine
        from core.models import StrategyConfig, RiskConfig
        from core.broker import ConsoleBroker
        cfg = StrategyConfig(min_vwap_room_rr=1.5)
        risk = RiskConfig()
        broker = ConsoleBroker()
        engine = BaseStrategyEngine(
            cfg=cfg, risk=risk, broker=broker, signal_provider=StubSignalProvider(),
        )
        engine.state.ce_symbol = "NIFTY08AUG2625000CE"
        engine.state.pe_symbol = "NIFTY08AUG2625000PE"
        assert engine.state.ce_symbol == "NIFTY08AUG2625000CE"
        assert engine.state.pe_symbol == "NIFTY08AUG2625000PE"

    def test_get_status_snapshot(self):
        from core.engine import BaseStrategyEngine
        from core.models import StrategyConfig, RiskConfig
        from core.broker import ConsoleBroker
        cfg = StrategyConfig(min_vwap_room_rr=1.5)
        risk = RiskConfig()
        broker = ConsoleBroker()
        engine = BaseStrategyEngine(
            cfg=cfg, risk=risk, broker=broker, signal_provider=StubSignalProvider(),
        )
        snapshot = engine.get_status_snapshot()
        assert isinstance(snapshot, dict)

    def test_get_status_snapshot_with_state(self):
        from core.engine import BaseStrategyEngine
        from core.models import StrategyConfig, RiskConfig
        from core.broker import ConsoleBroker
        cfg = StrategyConfig(min_vwap_room_rr=1.5)
        risk = RiskConfig()
        broker = ConsoleBroker()
        engine = BaseStrategyEngine(
            cfg=cfg, risk=risk, broker=broker, signal_provider=StubSignalProvider(),
        )
        engine.state.atm_locked = True
        snapshot = engine.get_status_snapshot()
        assert isinstance(snapshot, dict)

    def test_get_status_snapshot_with_symbols(self):
        from core.engine import BaseStrategyEngine
        from core.models import StrategyConfig, RiskConfig
        from core.broker import ConsoleBroker
        cfg = StrategyConfig(min_vwap_room_rr=1.5)
        risk = RiskConfig()
        broker = ConsoleBroker()
        engine = BaseStrategyEngine(
            cfg=cfg, risk=risk, broker=broker, signal_provider=StubSignalProvider(),
        )
        engine.state.ce_symbol = "NIFTY08AUG2625000CE"
        engine.state.pe_symbol = "NIFTY08AUG2625000PE"
        snapshot = engine.get_status_snapshot()
        assert isinstance(snapshot, dict)