#!/usr/bin/env python3
"""
Real-time live dashboard showing status from all 3 strategy instruments.
Monitors log files and displays consolidated view.
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def find_latest_run_dir() -> Optional[str]:
    """Find the latest run directory."""
    logs_dir = Path("logs/live_runs")
    if not logs_dir.exists():
        return None
    
    run_dirs = sorted([d for d in logs_dir.iterdir() if d.is_dir()])
    return str(run_dirs[-1]) if run_dirs else None


def extract_last_table(log_file: Path) -> Optional[str]:
    """Extract the last table display from a log file."""
    if not log_file.exists():
        return None
    
    try:
        with open(log_file) as f:
            content = f.read()
    except Exception:
        return None
    
    # Find the last occurrence of the table (starting with ════)
    lines = content.split('\n')
    table_lines = []
    in_table = False
    
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith('════'):
            if not in_table:
                in_table = True
            else:
                # Found the start of the table, break
                break
        
        if in_table:
            table_lines.insert(0, lines[i])
    
    if table_lines and len(table_lines) > 3:
        return '\n'.join(table_lines)
    
    return None


def display_dashboard(run_dir: str) -> None:
    """Display consolidated dashboard from all instruments."""
    symbols = ['nifty', 'banknifty', 'sensex']
    log_files = {
        symbol: Path(run_dir) / f"{symbol}.log"
        for symbol in symbols
    }
    
    print("\033[2J\033[H")  # Clear screen
    print("=" * 95)
    print(f"  📊 LIVE TRADING DASHBOARD  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 95)
    print()
    
    tables_found = 0
    for symbol in symbols:
        log_file = log_files[symbol]
        table = extract_last_table(log_file)
        if table:
            print(table)
            print()
            tables_found += 1
    
    if tables_found == 0:
        print("  ⏳ Waiting for data... (strategies initializing)")
        print()
    
    print("=" * 95)
    print("  Press Ctrl+C to stop monitoring")
    print("=" * 95)


def main():
    """Main dashboard loop."""
    run_dir = find_latest_run_dir()
    
    if not run_dir:
        print("❌ No run directory found. Start the launcher first:")
        print("   MODE=live ./run_all_indices.sh")
        sys.exit(1)
    
    print(f"📁 Monitoring run: {run_dir}")
    print("Press Ctrl+C to exit...")
    time.sleep(2)
    
    try:
        while True:
            display_dashboard(run_dir)
            time.sleep(5)  # Refresh every 5 seconds
    except KeyboardInterrupt:
        print("\n✅ Dashboard stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
