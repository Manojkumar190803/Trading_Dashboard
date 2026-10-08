"""
Real-time signal logging for dashboard display.
Captures setup/candle signals from strategies and persists as JSON for frontend consumption.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("core.signal_logger")


class SignalLogger:
    """Log strategy signals (setup, candle, entry) for real-time dashboard display."""

    LOGS_DIR = Path("logs")
    SIGNAL_LOG_FILE = "ema21_3min_logs.json"

    @classmethod
    def init(cls) -> None:
        """Ensure logs directory exists."""
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def log_signal(
        cls,
        strategy: str,
        side: str,
        signal_type: str,  # "setup", "candle", "entry", "exit"
        symbol: str,
        message: str,
        level: str = "INFO",  # INFO, SUCCESS, WARNING, ERROR
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Log a strategy signal to the dashboard JSON file.

        Args:
            strategy: Strategy name (e.g., "EMA21", "HD")
            side: "CE" or "PE"
            signal_type: Type of signal ("setup", "candle", "entry", "exit")
            symbol: Option symbol or instrument
            message: Full signal message
            level: Log level
            timestamp: Override timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()

        cls.init()

        # Read existing logs
        log_file = cls.LOGS_DIR / cls.SIGNAL_LOG_FILE
        logs = cls._read_logs(log_file)

        # Create new entry
        entry = {
            "id": f"sig-{len(logs) + 1:04d}",
            "timestamp": timestamp.isoformat(),
            "level": level,
            "message": message,
            "strategy": strategy,
            "side": side,
            "signal_type": signal_type,
            "symbol": symbol,
        }

        # Append and keep latest N entries (limit to 500)
        logs.append(entry)
        if len(logs) > 500:
            logs = logs[-500:]

        # Write back to file
        try:
            log_file.write_text(
                json.dumps({"logs": logs}, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"Could not write signal log: {exc}")

    @classmethod
    def log_setup_detected(
        cls,
        strategy: str,
        side: str,
        symbol: str,
        candle_time: datetime,
    ) -> None:
        """Log when a setup is detected."""
        message = f"{strategy} Strategy: {side} setup detected - {symbol}"
        cls.log_signal(
            strategy=strategy,
            side=side,
            signal_type="setup",
            symbol=symbol,
            message=message,
            level="INFO",
            timestamp=candle_time,
        )

    @classmethod
    def log_candle_completed(
        cls,
        strategy: str,
        side: str,
        symbol: str,
        candle_time: datetime,
    ) -> None:
        """Log when a 3-minute candle completes."""
        message = f"{strategy} Strategy: {side} candle completed - {symbol}"
        cls.log_signal(
            strategy=strategy,
            side=side,
            signal_type="candle",
            symbol=symbol,
            message=message,
            level="SUCCESS",
            timestamp=candle_time,
        )

    @classmethod
    def log_entry(
        cls,
        strategy: str,
        side: str,
        symbol: str,
        price: float,
        quantity: int,
        timestamp: datetime,
    ) -> None:
        """Log when an entry is executed."""
        message = f"{strategy} Strategy: Entered {side} {symbol} @ {price:.2f} qty={quantity}"
        cls.log_signal(
            strategy=strategy,
            side=side,
            signal_type="entry",
            symbol=symbol,
            message=message,
            level="SUCCESS",
            timestamp=timestamp,
        )

    @classmethod
    def clear_logs(cls) -> None:
        """Clear all signal logs."""
        log_file = cls.LOGS_DIR / cls.SIGNAL_LOG_FILE
        try:
            log_file.write_text(json.dumps({"logs": []}, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Could not clear signal log: {exc}")

    @classmethod
    def _read_logs(cls, log_file: Path) -> list[Dict[str, Any]]:
        """Read existing logs from file."""
        if not log_file.exists():
            return []
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            return data.get("logs", [])
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"Could not read signal log: {exc}")
            return []
