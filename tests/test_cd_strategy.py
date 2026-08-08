"""Tests for the CD (Classic Divergence) strategy signal logic."""

from datetime import datetime
from typing import Optional

import pandas as pd
import pytest

from core.broker import ConsoleBroker
from core.engine import BaseStrategyEngine
from core.models import BaseSideState, RiskConfig, Signal, StrategyConfig
from strategies.cd import CDConfig, CDSideState, CDSignalProvider


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row(
    open_=50.0, high=55.0, low=45.0, close=54.0, rsi3=15.0,
    ema13=50.0, ema20=48.0, ema50=46.0, vwap=52.0, volume=1000,
    dt=None,
) -> pd.Series:
    return pd.Series({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "rsi3": rsi3,
        "ema13": ema13,
        "ema20": ema20,
        "ema50": ema50,
        "vwap": vwap,
        "volume": volume,
        "datetime": dt or datetime(2026, 8, 8, 10, 0),
    })


def _strong_green_row(low=45.0, rsi3=25.0) -> pd.Series:
    """Body >= 85% of range, green candle. Open near low, close near high."""
    high = 55.0
    return _row(open_=low + 0.1, high=high, low=low, close=high - 0.1, rsi3=rsi3)


def _hammer_row(low=40.0, rsi3=25.0) -> pd.Series:
    """Lower wick >= 2x body, green. Body near top of range."""
    high = 55.0
    open_ = 53.0
    close = 54.0
    return _row(open_=open_, high=high, low=low, close=close, rsi3=rsi3)


def _red_row(rsi3=25.0) -> pd.Series:
    return _row(open_=54.0, high=55.0, low=45.0, close=46.0, rsi3=rsi3)


def _setup_divergence(provider: CDSignalProvider, ss: CDSideState) -> None:
    """Manually walk through the state machine to arm classic divergence.

    P1: price=45, rsi=10 (first sub-20 excursion)
    P2: price=42, rsi=12 (Price LL, RSI HL → classic divergence)
    """
    # Candle 1: RSI crosses below 20
    row1 = _row(low=45.0, rsi3=15.0)
    prev1 = _row(rsi3=22.0)
    provider.update_state(ss, row1, prev1)

    # Candle 2: RSI stays below 20, deeper low
    row2 = _row(low=44.0, rsi3=10.0)
    provider.update_state(ss, row2, row1)

    # Candle 3: RSI crosses above 20 → P1 locked (price=44, rsi=10)
    row3 = _row(low=50.0, rsi3=22.0)
    provider.update_state(ss, row3, row2)
    assert ss.p1_price == 44.0
    assert ss.p1_rsi == 10.0

    # Candle 4: RSI crosses below 20 again (new excursion)
    row4 = _row(low=42.0, rsi3=18.0)
    prev4 = _row(rsi3=22.0)
    provider.update_state(ss, row4, prev4)

    # Candle 5: Deeper RSI low but higher than P1's RSI
    row5 = _row(low=41.0, rsi3=12.0)
    provider.update_state(ss, row5, row4)

    # Candle 6: RSI crosses above 20 → P2 locked (price=41, rsi=12)
    # Classic: P2_price(41) < P1_price(44) AND P2_rsi(12) > P1_rsi(10) ✓
    row6 = _row(low=50.0, rsi3=22.0)
    provider.update_state(ss, row6, row5)
    assert ss.p2_price == 41.0
    assert ss.p2_rsi == 12.0
    assert ss.divergence_ready is True


# ═══════════════════════════════════════════════════════════════════════════════
# Divergence detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestCDDivergenceDetection:
    def test_classic_divergence_armed_correctly(self):
        """Price LL + RSI HL should arm divergence_ready."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)
        assert ss.divergence_ready is True

    def test_hidden_divergence_does_not_arm(self):
        """Price HL + RSI LL (HD pattern) should NOT arm CD divergence."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()

        # P1: price=44, rsi=10
        row1 = _row(low=44.0, rsi3=15.0)
        prev1 = _row(rsi3=22.0)
        provider.update_state(ss, row1, prev1)
        row2 = _row(low=44.0, rsi3=10.0)
        provider.update_state(ss, row2, row1)
        row3 = _row(low=50.0, rsi3=22.0)
        provider.update_state(ss, row3, row2)

        # P2: price=46 (HL), rsi=8 (LL) — this is HD, not CD
        row4 = _row(low=46.0, rsi3=18.0)
        prev4 = _row(rsi3=22.0)
        provider.update_state(ss, row4, prev4)
        row5 = _row(low=46.0, rsi3=8.0)
        provider.update_state(ss, row5, row4)
        row6 = _row(low=50.0, rsi3=22.0)
        provider.update_state(ss, row6, row5)

        assert ss.divergence_ready is False

    def test_no_divergence_equal_price(self):
        """Equal price (not LL) should not arm."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()

        # P1: price=44, rsi=10
        row1 = _row(low=44.0, rsi3=15.0)
        prev1 = _row(rsi3=22.0)
        provider.update_state(ss, row1, prev1)
        row2 = _row(low=44.0, rsi3=10.0)
        provider.update_state(ss, row2, row1)
        row3 = _row(low=50.0, rsi3=22.0)
        provider.update_state(ss, row3, row2)

        # P2: price=44 (equal, not LL), rsi=12 (HL)
        row4 = _row(low=44.0, rsi3=18.0)
        prev4 = _row(rsi3=22.0)
        provider.update_state(ss, row4, prev4)
        row5 = _row(low=44.0, rsi3=12.0)
        provider.update_state(ss, row5, row4)
        row6 = _row(low=50.0, rsi3=22.0)
        provider.update_state(ss, row6, row5)

        assert ss.divergence_ready is False


# ═══════════════════════════════════════════════════════════════════════════════
# Dual-candle confirmation
# ═══════════════════════════════════════════════════════════════════════════════


class TestDualCandleConfirmation:
    def test_two_strong_green_candles_confirm(self):
        """Two consecutive strong green candles → signal fires."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        # Confirmation candle +1
        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)
        assert ss.confirm_count == 1

        # Confirmation candle +2
        c2 = _strong_green_row(low=44.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)
        assert ss.confirm_count == 2

        sig = provider.generate_signal("CE", ss, c2, c1)
        assert sig == Signal.BUY_CE

    def test_two_hammer_candles_confirm(self):
        """Two consecutive hammer candles → signal fires."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        c1 = _hammer_row(low=38.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        c2 = _hammer_row(low=39.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)
        assert ss.confirm_count == 2

        sig = provider.generate_signal("PE", ss, c2, c1)
        assert sig == Signal.BUY_PE

    def test_mixed_strong_green_and_hammer_confirm(self):
        """One strong green + one hammer → signal fires."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        c2 = _hammer_row(low=39.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)
        assert ss.confirm_count == 2

    def test_red_candle_invalidates_and_resets(self):
        """A red candle during confirmation resets entire divergence state."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        # First confirm candle OK
        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)
        assert ss.confirm_count == 1

        # Red candle invalidates
        c2 = _red_row(rsi3=28.0)
        provider.update_state(ss, c2, c1)
        assert ss.confirm_count == 0
        assert ss.divergence_ready is False
        assert ss.p1_price is None
        assert ss.p2_price is None

    def test_doji_candle_invalidates(self):
        """A doji (open==close, not strong green or hammer) invalidates."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        # Doji: open == close
        doji = _row(open_=50.0, high=55.0, low=45.0, close=50.0, rsi3=25.0)
        prev = _row(rsi3=22.0)
        provider.update_state(ss, doji, prev)
        assert ss.confirm_count == 0
        assert ss.divergence_ready is False

    def test_no_signal_before_confirmation(self):
        """Divergence armed but no confirmation candles → no signal."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        row = _row(rsi3=22.0)
        sig = provider.generate_signal("CE", ss, row, None)
        assert sig == Signal.NONE

    def test_one_candle_confirmed_no_signal(self):
        """Only 1/2 confirmation candles → no signal yet."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        sig = provider.generate_signal("CE", ss, c1, prev_c1)
        assert sig == Signal.NONE


# ═══════════════════════════════════════════════════════════════════════════════
# Risk computation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCDRiskComputation:
    def test_stop_level_uses_lowest_of_p1_p2_and_confirms(self):
        """SL = min(P1_low, P2_low, confirm_candle_lows) - 1.0."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        # P1_price=44, P2_price=41
        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        c2 = _strong_green_row(low=39.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)

        # Lowest is confirm candle 2 low=39.0, so SL=38.0
        stop = provider.compute_stop_level(ss, c2)
        assert stop == pytest.approx(38.0)

    def test_risk_points_formula(self):
        """Risk = Entry(high+1) - SL."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        c2 = _strong_green_row(low=44.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)

        # c2 high=55, entry=56. Lowest low = P2=41, SL=40. Risk=56-40=16
        risk = provider.compute_risk_points(ss, c2)
        assert risk == pytest.approx(16.0)

    def test_entry_lots_above_vwap(self):
        """Close > VWAP → 2 lots."""
        provider = CDSignalProvider()
        cfg = StrategyConfig()
        row = _row(close=55.0, vwap=50.0)
        assert provider.compute_entry_lots(row, cfg) == cfg.full_size_lots

    def test_entry_lots_below_vwap(self):
        """Close < VWAP → 1 lot."""
        provider = CDSignalProvider()
        cfg = StrategyConfig()
        row = _row(close=48.0, vwap=50.0)
        assert provider.compute_entry_lots(row, cfg) == cfg.half_size_lots


# ═══════════════════════════════════════════════════════════════════════════════
# Engine integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestCDEngineIntegration:
    def _make_engine(self):
        cfg = StrategyConfig()
        risk = RiskConfig()
        broker = ConsoleBroker()
        provider = CDSignalProvider(CDConfig())
        engine = BaseStrategyEngine(cfg=cfg, risk=risk, broker=broker, signal_provider=provider)
        from datetime import date
        engine.reset_for_new_day(date(2026, 8, 8))
        engine.state.atm_locked = True
        engine.state.ce_symbol = "NIFTY08AUG2625000CE"
        engine.state.pe_symbol = "NIFTY08AUG2625000PE"
        engine.state.ce.option_symbol = "NIFTY08AUG2625000CE"
        engine.state.pe.option_symbol = "NIFTY08AUG2625000PE"
        return engine

    def test_full_signal_to_entry_flow(self):
        """Divergence + 2 confirm candles → pending entry placed."""
        engine = self._make_engine()
        ss = engine.state.ce
        provider = engine.signal_provider
        assert isinstance(provider, CDSignalProvider)

        _setup_divergence(provider, ss)

        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        c2 = _strong_green_row(low=44.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)

        sig = provider.generate_signal("CE", ss, c2, c1)
        assert sig == Signal.BUY_CE

        ts = datetime(2026, 8, 8, 10, 15)
        engine.place_pending_entry("CE", ss, ts, c2)
        assert ss.pending_entry is not None
        assert ss.pending_entry.option_symbol == "NIFTY08AUG2625000CE"

    def test_risk_cap_rejects_wide_stop(self):
        """If risk > 20 points, entry is discarded."""
        engine = self._make_engine()
        ss = engine.state.ce
        provider = engine.signal_provider
        assert isinstance(provider, CDSignalProvider)

        _setup_divergence(provider, ss)

        # Use a very low confirm low to make risk > 20
        c1 = _strong_green_row(low=30.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)

        c2 = _strong_green_row(low=44.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)

        # entry=high(55)+1=56, SL=min(44,41,30,44)-1=29. Risk=56-29=27 > 20
        ts = datetime(2026, 8, 8, 10, 15)
        engine.place_pending_entry("CE", ss, ts, c2)
        assert ss.pending_entry is None
        assert any("risk" in a.message.lower() for a in engine.alerts)

    def test_reset_after_entry_clears_state(self):
        """After entry placement, divergence state is fully reset."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)
        c2 = _strong_green_row(low=44.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)

        provider.reset_after_entry(ss)
        assert ss.p1_price is None
        assert ss.p2_price is None
        assert ss.divergence_ready is False
        assert ss.confirm_count == 0
        assert ss.confirm_lows == []

    def test_no_signal_when_position_active(self):
        """No new signal generated if position already exists."""
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)

        c1 = _strong_green_row(low=43.0, rsi3=25.0)
        prev_c1 = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev_c1)
        c2 = _strong_green_row(low=44.0, rsi3=30.0)
        provider.update_state(ss, c2, c1)

        # Simulate active position
        from core.models import Position
        ss.position = Position(
            option_symbol="NIFTY08AUG2625000CE",
            option_type="CE",
            quantity=65,
            initial_quantity=65,
            entry_price=56.0,
            entry_time=datetime(2026, 8, 8, 10, 0),
            option_stop_level=40.0,
            option_entry_trigger=56.0,
            option_risk_points=16.0,
        )
        sig = provider.generate_signal("CE", ss, c2, c1)
        assert sig == Signal.NONE


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostic output
# ═══════════════════════════════════════════════════════════════════════════════


class TestCDDiagnostics:
    def test_diagnose_no_p1(self):
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        row = _row(rsi3=25.0)
        diag = provider.diagnose_no_signal("CE", ss, row, None)
        assert "NO_P1" in diag

    def test_diagnose_no_p2(self):
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        ss.p1_price = 44.0
        ss.p1_rsi = 10.0
        row = _row(rsi3=25.0)
        diag = provider.diagnose_no_signal("CE", ss, row, None)
        assert "NO_P2" in diag

    def test_diagnose_divergence_not_armed(self):
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        ss.p1_price = 44.0
        ss.p1_rsi = 10.0
        ss.p2_price = 46.0  # Not LL
        ss.p2_rsi = 12.0
        ss.divergence_ready = False
        row = _row(rsi3=25.0)
        diag = provider.diagnose_no_signal("CE", ss, row, None)
        assert "DIV_NOT_ARMED" in diag

    def test_diagnose_confirm_pending(self):
        provider = CDSignalProvider()
        ss = provider.create_side_state()
        _setup_divergence(provider, ss)
        c1 = _strong_green_row(rsi3=25.0)
        prev = _row(rsi3=22.0)
        provider.update_state(ss, c1, prev)

        row = _row(rsi3=28.0)
        diag = provider.diagnose_no_signal("CE", ss, row, None)
        assert "CONFIRM_PENDING" in diag
