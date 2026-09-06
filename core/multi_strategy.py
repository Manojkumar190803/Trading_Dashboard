from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import pandas as pd

from core.engine import BaseStrategyEngine
from core.models import RiskConfig, StrategyConfig
from core.broker import BrokerInterface
from strategies.cd import CDSignalProvider
from strategies.ema21 import EMA21SignalProvider
from strategies.hd import HDSignalProvider
from strategies.tc import TCSignalProvider


@dataclass(frozen=True)
class StrategyDefinition:
    key: str
    label: str
    provider_factory: Callable[[], Any]


STRATEGY_DEFINITIONS: tuple[StrategyDefinition, ...] = (
    StrategyDefinition("hd", "HD Strategy", HDSignalProvider),
    StrategyDefinition("cd", "CD Strategy", CDSignalProvider),
    StrategyDefinition("tc", "TC Strategy", TCSignalProvider),
    StrategyDefinition("ema21", "21EMA Strategy", EMA21SignalProvider),
)


class MultiStrategyRuntime:
    """Run independent provider engines over one shared candle feed."""

    def __init__(
        self,
        cfg: StrategyConfig,
        risk: RiskConfig,
        broker: BrokerInterface,
        enabled_keys: Optional[list[str]] = None,
    ) -> None:
        self.cfg = cfg
        self.risk = risk
        self.broker = broker
        self._engines: dict[str, BaseStrategyEngine] = {}
        self.engines: dict[str, BaseStrategyEngine] = {}
        self._last_candle_time: dict[str, Any] = {}
        self.set_enabled(enabled_keys or ["hd"])

    def set_enabled(self, enabled_keys: list[str]) -> None:
        definitions = {definition.key: definition for definition in STRATEGY_DEFINITIONS}
        selected = [key for key in enabled_keys if key in definitions]
        for key in selected:
            if key not in self._engines:
                definition = definitions[key]
                self._engines[key] = BaseStrategyEngine(
                    self.cfg,
                    self.risk,
                    self.broker,
                    definition.provider_factory(),
                )
        self.engines = {key: self._engines[key] for key in selected}

    def process_candle(
        self,
        row: pd.Series,
        prev_row: Optional[pd.Series],
        option_frames: Optional[dict[str, dict[str, pd.DataFrame]]] = None,
    ) -> list[str]:
        """Process a spot candle once for each enabled strategy.

        Option frames are keyed by strategy key and are intentionally optional;
        engines that have not locked an option contract can process the spot row.
        """
        processed: list[str] = []
        candle_time = row.get("datetime")
        for key, engine in self.engines.items():
            if candle_time is not None and self._last_candle_time.get(key) == candle_time:
                continue
            frames = (option_frames or {}).get(key, {})
            processed_option = False
            if frames and engine.state.atm_locked:
                for side in ("CE", "PE"):
                    side_frame = frames.get(side)
                    if side_frame is None or side_frame.empty:
                        continue
                    matches = side_frame[
                        pd.to_datetime(side_frame["datetime"], errors="coerce")
                        == pd.to_datetime(candle_time)
                    ]
                    if not matches.empty:
                        position = int(matches.index[-1])
                        side_row = matches.iloc[-1]
                        side_prev = side_frame.iloc[position - 1] if position > 0 else None
                        engine.process_option_candle(side, side_row, side_prev)
                        processed_option = True
            if not processed_option:
                engine.process_candle(row, prev_row)
            self._last_candle_time[key] = candle_time
            processed.append(key)
        return processed

    def snapshots(self) -> dict[str, dict[str, Any]]:
        return {key: engine.get_status_snapshot() for key, engine in self.engines.items()}

    @property
    def active_keys(self) -> tuple[str, ...]:
        return tuple(self.engines)
