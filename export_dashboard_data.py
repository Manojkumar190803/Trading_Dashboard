#!/usr/bin/env python3
"""
Export real OpenAlgo account data for React dashboard.
Run this as a daemon or cron job to continuously update dashboard_data.json and wallet_data.json
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from core.dashboard_data import DashboardDataProvider

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent / 'logs' / 'dashboard_export.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("dashboard_export")


def main(mode: str = "analyzer", interval: int = 5):
    """
    Continuously export dashboard data.
    
    Args:
        mode: Retained for compatibility; account data always comes from configured OpenAlgo.
        interval: Export interval in seconds
    """
    logger.info(f"Starting dashboard export daemon - mode={mode}, interval={interval}s")
    
    dashboard_provider = DashboardDataProvider(
        api_key=os.getenv("OPENALGO_API_KEY", ""),
        host=os.getenv("OPENALGO_HOST", "http://127.0.0.1:5002"),
    )

    try:
        while True:
            try:
                dashboard_provider.write_dashboard_json()
            except Exception:
                logger.exception("Could not export OpenAlgo dashboard data")
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Dashboard export daemon stopped")
    except Exception as e:
        logger.error(f"Dashboard export daemon error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else os.getenv("STRATEGY_MODE", "analyzer")
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.getenv("EXPORT_INTERVAL", "5"))
    
    main(mode, interval)
