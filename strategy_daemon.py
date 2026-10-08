"""
Strategy Daemon - Auto-starts and monitors strategies based on React dashboard configuration.

This daemon:
1. Watches logs/instruments_config.json for instrument changes
2. Auto-starts/stops strategies based on instrument status
3. Updates logs/strategies_status.json with running status
4. Bridges React dashboard with Python strategy engine
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s: %(message)s'
)
logger = logging.getLogger('strategy_daemon')

LOGS_DIR = Path(os.getenv('LOGS_DIR', 'logs'))
CONFIG_FILE = LOGS_DIR / 'instruments_config.json'
STATUS_FILE = LOGS_DIR / 'strategies_status.json'
SCRIPTS_PID_FILE = LOGS_DIR / '.strategy_pids.json'

# Track running processes
running_processes: dict[str, subprocess.Popen] = {}
running_status: dict[str, Any] = {}


def _load_config() -> dict[str, Any]:
    """Load instruments config from React dashboard export."""
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load config: {e}")
    return {'instruments': []}


def _save_status() -> None:
    """Save current running strategies status."""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        status = {
            'updated_at': datetime.now().isoformat(),
            'running_strategies': running_status,
        }
        STATUS_FILE.write_text(json.dumps(status, indent=2), encoding='utf-8')
    except OSError as e:
        logger.error(f"Failed to save status: {e}")


def _build_command(instrument: dict[str, Any]) -> list[str]:
    """Build the CLI command to run a strategy for an instrument."""
    script = instrument.get('brokerSymbol', 'NIFTY').upper()
    strategy_name = instrument.get('strategy', '21EMA')
    
    # Map React strategy names (from UI) to run_strategy.py registry names
    STRATEGY_NAME_MAP = {
        '21EMA': 'ema21',      # Special case: React uses 21EMA, registry uses ema21
        '21ema': 'ema21',      # Handle lowercase variant
        'HD': 'hd',
        'hd': 'hd',
        'CD': 'cd',
        'cd': 'cd',
        'TC': 'tc',
        'tc': 'tc',
        '2BC': '2bc',
        '2bc': '2bc',
        'BO': 'bo',
        'bo': 'bo',
    }
    
    strategy = STRATEGY_NAME_MAP.get(strategy_name, strategy_name.lower())
    
    cmd = [
        'python3',
        'run_strategy.py',
        '--script', script,
        '--strategy', strategy,
        '--mode', 'live',
    ]
    
    return cmd


def _start_strategy(instrument: dict[str, Any]) -> Optional[subprocess.Popen]:
    """Start monitoring a strategy for the given instrument."""
    inst_id = instrument.get('id', 'unknown')
    inst_name = instrument.get('name', 'Unknown')
    strategy = instrument.get('strategy', 'unknown')
    
    # Don't re-start if already running
    if inst_id in running_processes:
        logger.info(f"Strategy {inst_name} ({strategy}) already running")
        return None
    
    try:
        cmd = _build_command(instrument)
        logger.info(f"Starting strategy for {inst_name} ({strategy}): {' '.join(cmd)}")
        
        # Start the process
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'},
        )
        
        running_processes[inst_id] = proc
        running_status[inst_id] = {
            'instrument_name': inst_name,
            'strategy': strategy,
            'pid': proc.pid,
            'started_at': datetime.now().isoformat(),
            'status': 'running',
        }
        
        logger.info(f"Started {inst_name} (PID: {proc.pid})")
        return proc
    except Exception as e:
        logger.error(f"Failed to start strategy for {inst_name}: {e}")
        running_status[inst_id] = {
            'instrument_name': inst_name,
            'strategy': strategy,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat(),
        }
        return None


def _stop_strategy(inst_id: str) -> None:
    """Stop monitoring a strategy."""
    if inst_id not in running_processes:
        return
    
    try:
        proc = running_processes[inst_id]
        inst_name = running_status.get(inst_id, {}).get('instrument_name', inst_id)
        
        logger.info(f"Stopping strategy {inst_name} (PID: {proc.pid})")
        proc.terminate()
        
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning(f"Force killing {inst_name} (PID: {proc.pid})")
            proc.kill()
            proc.wait()
        
        del running_processes[inst_id]
        if inst_id in running_status:
            running_status[inst_id]['status'] = 'stopped'
            running_status[inst_id]['stopped_at'] = datetime.now().isoformat()
        
        logger.info(f"Stopped {inst_name}")
    except Exception as e:
        logger.error(f"Failed to stop strategy {inst_id}: {e}")


def _monitor_health() -> None:
    """Monitor running processes and restart if crashed."""
    while True:
        try:
            time.sleep(10)  # Check every 10 seconds
            
            # Check if any processes have died
            dead_pids = []
            for inst_id, proc in list(running_processes.items()):
                if proc.poll() is not None:  # Process has terminated
                    logger.warning(f"Strategy {inst_id} (PID: {proc.pid}) crashed")
                    dead_pids.append(inst_id)
                    if inst_id in running_status:
                        running_status[inst_id]['status'] = 'crashed'
                        running_status[inst_id]['crashed_at'] = datetime.now().isoformat()
            
            # Remove dead processes
            for inst_id in dead_pids:
                del running_processes[inst_id]
            
            if dead_pids:
                _save_status()
        except Exception as e:
            logger.error(f"Health check error: {e}")


def monitor_instruments() -> None:
    """Main loop: monitor config file and manage strategy lifecycle."""
    last_config: dict[str, Any] = {}
    
    # Start health monitoring thread
    health_thread = threading.Thread(target=_monitor_health, daemon=True)
    health_thread.start()
    
    logger.info("Strategy daemon started. Watching for instrument changes...")
    
    while True:
        try:
            time.sleep(5)  # Check every 5 seconds
            
            # Load current config
            current_config = _load_config()
            current_instruments = {
                inst['id']: inst for inst in current_config.get('instruments', [])
            }
            last_instruments = {
                inst['id']: inst for inst in last_config.get('instruments', [])
            }
            
            # Find new or toggled instruments
            for inst_id, instrument in current_instruments.items():
                was_active = last_instruments.get(inst_id, {}).get('status', False)
                is_active = instrument.get('status', False)
                
                if is_active and not was_active:
                    # Instrument just became active
                    _start_strategy(instrument)
                elif not is_active and was_active:
                    # Instrument just became inactive
                    _stop_strategy(inst_id)
            
            # Find removed instruments
            for inst_id in last_instruments:
                if inst_id not in current_instruments:
                    _stop_strategy(inst_id)
            
            # Save status
            _save_status()
            
            # Update last config
            last_config = current_config
        except KeyboardInterrupt:
            logger.info("Daemon interrupted by user")
            break
        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
    
    # Cleanup: stop all running strategies
    logger.info("Shutting down all strategies...")
    for inst_id in list(running_processes.keys()):
        _stop_strategy(inst_id)
    
    _save_status()
    logger.info("Strategy daemon stopped")


if __name__ == '__main__':
    try:
        monitor_instruments()
    except Exception as e:
        logger.exception("Daemon crashed: %s", e)
        sys.exit(1)
