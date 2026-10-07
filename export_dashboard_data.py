#!/usr/bin/env python3
"""
Export real OpenAlgo account data for React dashboard.
Run this as a daemon or cron job to continuously update dashboard_data.json and wallet_data.json
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.dashboard_data import DashboardDataProvider, FyersWalletProvider, export_dashboard_data

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
        mode: 'analyzer' (OpenAlgo) or 'live' (Fyers)
        interval: Export interval in seconds
    """
    logger.info(f"Starting dashboard export daemon - mode={mode}, interval={interval}s")
    
    dashboard_provider = DashboardDataProvider(
        api_key=os.getenv("OPENALGO_API_KEY", "demo"),
        host=os.getenv("OPENALGO_HOST", "http://localhost:5010"),
    )
    
    wallet_provider = FyersWalletProvider(
        fyers_api_key=os.getenv("FYERS_API_KEY"),
        fyers_access_token=os.getenv("FYERS_ACCESS_TOKEN"),
    )
    
    try:
        while True:
            logger.debug(f"Exporting dashboard data...")
            
            # Export OpenAlgo data (always for analyzer mode)
            if mode.lower() in ["analyzer", "both"]:
                dashboard_provider.write_dashboard_json()
            
            # Export Fyers data (for live mode)
            if mode.lower() in ["live", "both"]:
                wallet_provider.write_wallet_json()
            
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
