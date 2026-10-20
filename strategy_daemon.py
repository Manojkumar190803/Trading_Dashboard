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
import fcntl
import logging
import os
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import urlopen

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s: %(message)s'
)
logger = logging.getLogger('strategy_daemon')

LOGS_DIR = Path(os.getenv('LOGS_DIR', 'logs'))
CONFIG_FILE = LOGS_DIR / 'instruments_config.json'
STATUS_FILE = LOGS_DIR / 'strategies_status.json'
SCRIPTS_PID_FILE = LOGS_DIR / '.strategy_pids.json'
DAEMON_LOCK_FILE = LOGS_DIR / '.strategy_daemon.lock'

# Track running processes
running_processes: dict[str, subprocess.Popen] = {}
running_status: dict[str, Any] = {}
process_log_handles: dict[str, Any] = {}


def _load_trailing_config() -> dict[str, Any]:
    try:
        if CONFIG_FILE.exists():
            payload = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            trailing = payload.get('trailingStopsConfig', {})
            return trailing if isinstance(trailing, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not load dashboard trailing settings: %s", exc)
    return {}


def _load_config() -> Optional[dict[str, Any]]:
    """Load active instruments from the dashboard API, or its local export."""
    api_url = os.getenv('STRATEGY_DASHBOARD_API_URL', '').strip()
    if api_url:
        try:
            with urlopen(api_url, timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
            if not isinstance(payload, dict) or not isinstance(payload.get('instruments'), list):
                logger.error("dashboard instrument API returned an invalid payload")
                return None
            payload['trailingStopsConfig'] = _load_trailing_config()
            return payload
        except (OSError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("dashboard instrument API unavailable; keeping current processes: %s", exc)
            return None

    try:
        if CONFIG_FILE.exists():
            payload = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            if isinstance(payload, dict) and isinstance(payload.get('instruments'), list):
                return payload
            logger.error("dashboard instrument export has an invalid shape")
            return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to load dashboard export: %s", exc)
        return None
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


def _managed_instruments(config: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    strategy_filter = {
        name.strip().upper()
        for name in os.getenv('STRATEGY_FILTER', '').split(',')
        if name.strip()
    }
    return {
        instrument['id']: instrument
        for instrument in config.get('instruments', [])
        if isinstance(instrument, dict)
        and 'id' in instrument
        and (
            instrument.get('status') is True
            or str(instrument.get('status', '')).upper() == 'ACTIVE'
        )
        and (
            not strategy_filter
            or str(instrument.get('strategy', '')).upper() in strategy_filter
        )
    }


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
        
        safe_id = ''.join(char if char.isalnum() or char in '-_' else '_' for char in str(inst_id))
        log_path = LOGS_DIR / f"strategy_{safe_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open('a', encoding='utf-8')
        proc = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=_strategy_environment(instrument, _current_trailing_config),
        )

        running_processes[inst_id] = proc
        process_log_handles[inst_id] = log_handle
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
        if 'log_handle' in locals():
            log_handle.close()
        logger.error(f"Failed to start strategy for {inst_name}: {e}")
        running_status[inst_id] = {
            'instrument_name': inst_name,
            'strategy': strategy,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat(),
        }
        return None


def _strategy_environment(
    instrument: dict[str, Any],
    trailing_config: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    environment = {**os.environ, 'PYTHONUNBUFFERED': '1'}
    strategy_key = str(instrument.get('strategy', '21EMA')).strip().upper()
    if strategy_key in {'21EMA', 'EMA21'}:
        strategy_key = 'EMA21'

    if strategy_key == 'EMA21':
        strategy_tag = environment.get('STRATEGY_NAME', 'Strategy')
    else:
        strategy_tag = strategy_key
    environment['STRATEGY_NAME'] = strategy_tag
    environment['SHARED_SL_COUNT_NAMESPACE'] = strategy_key
    if strategy_key != 'EMA21':
        environment.pop('SHARED_SL_COUNT_FILE', None)

    if strategy_key != 'HD':
        return environment

    trailing = trailing_config or {}
    lot_size_value = instrument.get('lotSizeAdjustment')
    lot_size_adjustment = float(1 if lot_size_value is None else lot_size_value)
    if lot_size_adjustment < 1 or not lot_size_adjustment.is_integer():
        raise ValueError('HD lotSizeAdjustment must be a positive integer')

    premium_min = instrument.get('premiumMinPrice')
    premium_max = instrument.get('premiumMaxPrice')
    max_initial_risk = instrument.get('maxInitialRiskPoints')
    if max_initial_risk is None:
        max_initial_risk = 20
    values = {
        'HD_PREMIUM_MIN_PRICE': 120 if premium_min is None else premium_min,
        'HD_PREMIUM_MAX_PRICE': 180 if premium_max is None else premium_max,
        'HD_MAX_OPTION_RISK_POINTS': max_initial_risk,
        'HD_FULL_SIZE_LOTS': int(lot_size_adjustment),
        'HD_MONITORING_START_TIME': instrument.get('monitoringStartTime') or '09:15',
        'HD_MONITORING_END_TIME': instrument.get('monitoringEndTime') or '15:30',
        'HD_ENTRY_CUTOFF': instrument.get('entryCutoffTime') or '14:40',
        'HD_BREAKEVEN_RR': trailing.get('breakEvenRR')
        if trailing.get('breakEvenRR') is not None else 1.25,
        'HD_TRAIL_STEP_RR': trailing.get('trailStepRR')
        if trailing.get('trailStepRR') is not None else 0.5,
    }
    environment.update({key: str(value) for key, value in values.items()})
    return environment


_current_trailing_config: dict[str, Any] = {}


def _acquire_singleton_lock() -> Optional[Any]:
    """Prevent a second manager from launching duplicate strategy processes."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handle = DAEMON_LOCK_FILE.open('a+', encoding='utf-8')
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None

    handle.seek(0)
    handle.truncate()
    handle.write(f'{os.getpid()}\n')
    handle.flush()
    return handle


def _runtime_signature(instrument: dict[str, Any], trailing: dict[str, Any]) -> tuple[object, ...]:
    return (
        instrument.get('strategy'),
        instrument.get('brokerSymbol'),
        instrument.get('monitoringStartTime'),
        instrument.get('premiumMinPrice'),
        instrument.get('premiumMaxPrice'),
        instrument.get('maxInitialRiskPoints'),
        instrument.get('lotSizeAdjustment'),
        instrument.get('entryCutoffTime'),
        instrument.get('monitoringEndTime'),
        trailing.get('breakEvenRR'),
        trailing.get('trailStepRR'),
    )


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
        log_handle = process_log_handles.pop(inst_id, None)
        if log_handle is not None:
            log_handle.close()
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
                log_handle = process_log_handles.pop(inst_id, None)
                if log_handle is not None:
                    log_handle.close()
            
            if dead_pids:
                _save_status()
        except Exception as e:
            logger.error(f"Health check error: {e}")


def monitor_instruments() -> None:
    """Main loop: monitor config file and manage strategy lifecycle."""
    global _current_trailing_config
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
            if current_config is None:
                continue
            _current_trailing_config = current_config.get('trailingStopsConfig', {})
            current_instruments = _managed_instruments(current_config)
            last_instruments = _managed_instruments(last_config)
            
            # Find new or toggled instruments
            for inst_id, instrument in current_instruments.items():
                was_active = inst_id in last_instruments
                
                if inst_id not in running_processes:
                    # Instrument just became active
                    _start_strategy(instrument)
                elif (
                    was_active
                    and _runtime_signature(instrument, _current_trailing_config)
                    != _runtime_signature(last_instruments.get(inst_id, {}), last_config.get('trailingStopsConfig', {}))
                ):
                    _stop_strategy(inst_id)
                    _start_strategy(instrument)
            
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
        daemon_lock = _acquire_singleton_lock()
    except OSError:
        logger.exception("could not acquire the strategy daemon lock")
        sys.exit(1)
    if daemon_lock is None:
        logger.error("another strategy daemon owns the shared logs directory; refusing to start")
        sys.exit(1)

    try:
        monitor_instruments()
    except Exception as e:
        logger.exception("Daemon crashed: %s", e)
        sys.exit(1)
    finally:
        daemon_lock.close()
