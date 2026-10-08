"""
AlertLogger: Centralized alert logging utility for strategy-triggered events.

Logs alerts when strategy rules are satisfied, capturing:
- Alert timestamp (UTC)
- Strategy name (EMA21, HD, etc.)
- Alert type (rule_triggered, setup, entry, exit, etc.)
- Symbol/instrument
- Alert message (human-readable description)
- Status (PENDING, CONFIRMED, ACTIONED, DISMISSED)

Maintains up to 500 most recent alerts per strategy.
File: logs/ema21_triggered_alerts.json (one file per strategy)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class AlertLogger:
    """Singleton for centralized alert logging to JSON file."""
    
    LOGS_DIR = Path("logs")
    ALERT_LOG_FILE = "ema21_triggered_alerts.json"
    MAX_ENTRIES = 500
    
    @classmethod
    def init(cls) -> None:
        """Initialize logs directory if it doesn't exist."""
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def log_alert(
        cls,
        strategy: str,
        alert_type: str,
        symbol: str,
        message: str,
        status: str = "PENDING",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Log an alert event to the alerts JSON file.
        
        Args:
            strategy: Strategy name (e.g., "EMA21")
            alert_type: Type of alert (e.g., "rule_triggered", "setup", "entry")
            symbol: Symbol/instrument (e.g., "NIFTY13OCT26225550CE")
            message: Human-readable alert message
            status: Alert status (PENDING, CONFIRMED, ACTIONED, DISMISSED)
            timestamp: Alert timestamp (defaults to now)
        """
        try:
            if timestamp is None:
                timestamp = datetime.utcnow()
            
            # Ensure logs directory exists
            cls.init()
            
            # Read existing alerts
            log_file = cls.LOGS_DIR / cls.ALERT_LOG_FILE
            alerts = cls._read_alerts(log_file)
            
            # Generate alert ID
            alert_id = f"alert-{len(alerts) + 1:04d}"
            
            # Create new alert entry
            new_alert = {
                "id": alert_id,
                "timestamp": timestamp.isoformat() + "Z" if not timestamp.isoformat().endswith("Z") else timestamp.isoformat(),
                "strategy": strategy,
                "alert_type": alert_type,
                "symbol": symbol,
                "message": message,
                "status": status,
            }
            
            # Append to alerts list
            alerts.append(new_alert)
            
            # Keep only most recent entries (FIFO - remove oldest if over limit)
            if len(alerts) > cls.MAX_ENTRIES:
                alerts = alerts[-cls.MAX_ENTRIES:]
            
            # Write back to file
            with open(log_file, "w") as f:
                json.dump({"alerts": alerts}, f, indent=2)
            
            logger.debug(f"Logged alert: {alert_id} - {message}")
        
        except (OSError, json.JSONDecodeError) as e:
            # Don't break strategy execution if logging fails
            logger.warning(f"Could not log alert: {e}")
    
    @classmethod
    def log_rule_triggered(
        cls,
        strategy: str,
        symbol: str,
        rule_name: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Log a rule-triggered alert (convenience wrapper).
        
        Args:
            strategy: Strategy name (e.g., "EMA21")
            symbol: Symbol/instrument
            rule_name: Name of the rule that triggered (e.g., "green_close_above_ema")
            message: Human-readable message
            timestamp: Alert timestamp (defaults to now)
        """
        cls.log_alert(
            strategy=strategy,
            alert_type="rule_triggered",
            symbol=symbol,
            message=message,
            status="PENDING",
            timestamp=timestamp,
        )
    
    @classmethod
    def log_setup_alert(
        cls,
        strategy: str,
        symbol: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Log a setup alert (convenience wrapper).
        
        Args:
            strategy: Strategy name
            symbol: Symbol/instrument
            message: Alert message describing the setup
            timestamp: Alert timestamp (defaults to now)
        """
        cls.log_alert(
            strategy=strategy,
            alert_type="setup",
            symbol=symbol,
            message=message,
            status="PENDING",
            timestamp=timestamp,
        )
    
    @classmethod
    def clear_alerts(cls) -> None:
        """Clear all alerts from the log file (used at backtest start)."""
        try:
            cls.init()
            log_file = cls.LOGS_DIR / cls.ALERT_LOG_FILE
            with open(log_file, "w") as f:
                json.dump({"alerts": []}, f, indent=2)
            logger.debug("Cleared all alerts")
        except OSError as e:
            logger.warning(f"Could not clear alerts: {e}")
    
    @classmethod
    def _read_alerts(cls, log_file: Path) -> list:
        """
        Read alerts from JSON file with error handling.
        
        Args:
            log_file: Path to alerts JSON file
            
        Returns:
            List of alert dictionaries, empty list if file doesn't exist or is invalid
        """
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, "r") as f:
                data = json.load(f)
                return data.get("alerts", [])
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {log_file}: {e}")
            return []
