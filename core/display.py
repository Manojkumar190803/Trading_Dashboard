"""Display utilities for formatted status output."""

import csv
import os
import sys
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def format_status_table(instrument: str, engines_status: dict[str, Any]) -> str:
    """Format strategy statuses with indicators: RSI, EMAs, VWAP, and trade status.
    
    Shows each strategy with detailed CE and PE status including technical indicators.
    """
    if not engines_status:
        return ""
    
    lines = []
    now = datetime.now()
    
    # Header with instrument and timestamp
    lines.append(f"┌──────────────────────────────────────────────────────────────────────────────────┐")
    lines.append(f"│ 📊 {instrument:<15} │ {now.strftime('%Y-%m-%d %H:%M:%S'):<35} │")
    lines.append(f"├─────────────────────────────────────────────────────────────────────────────────┤")
    lines.append(f"│ Strategy  │ CE Status                                                            │")
    lines.append(f"│           │ PE Status                                                            │")
    lines.append(f"├─────────────────────────────────────────────────────────────────────────────────┤")
    
    # Strategy rows
    for strategy_name in sorted(engines_status.keys()):
        status = engines_status[strategy_name]
        
        try:
            ce_status = _format_side_status_detailed(status.get("ce", {}))
            pe_status = _format_side_status_detailed(status.get("pe", {}))
        except Exception as e:
            ce_status = f"ERROR: {str(e)[:40]}"
            pe_status = f"ERROR: {str(e)[:40]}"
        
        # Format with proper alignment
        lines.append(f"│ {strategy_name:<9} │ {ce_status:<71} │")
        lines.append(f"│           │ {pe_status:<71} │")
    
    lines.append(f"└──────────────────────────────────────────────────────────────────────────────────┘")
    
    return "\n".join(lines)


def print_status_table(instrument: str, engines_status: dict[str, Any]) -> None:
    """Print status table with immediate flush for live terminal display.
    
    Ensures status updates appear immediately in terminal (every 3 minutes).
    """
    output = format_status_table(instrument, engines_status)
    if output:
        print(output, flush=True)
        sys.stdout.flush()


def _format_side_status_detailed(side_data: dict[str, Any]) -> str:
    """Format detailed status for a single side (CE/PE) with indicators.
    
    Shows RSI, EMA13/20/50, VWAP, and position status.
    Format: "RSI=45.5 E13=100.5 E20=99.5 E50=98.5 VWAP=99.0 | FLAT ▲"
    """
    if not side_data:
        return "RSI=-- E13=-- E20=-- E50=-- VWAP=-- | FLAT ▲"
    
    # Extract indicator values
    rsi = side_data.get("rsi")
    ema13 = side_data.get("ema13")
    ema20 = side_data.get("ema20")
    ema50 = side_data.get("ema50")
    vwap = side_data.get("vwap")
    
    # Format indicator part
    rsi_str = f"{rsi:.1f}" if rsi is not None else "--"
    e13_str = f"{ema13:.1f}" if ema13 is not None else "--"
    e20_str = f"{ema20:.1f}" if ema20 is not None else "--"
    e50_str = f"{ema50:.1f}" if ema50 is not None else "--"
    vwap_str = f"{vwap:.1f}" if vwap is not None else "--"
    
    indicators = f"RSI={rsi_str} E13={e13_str} E20={e20_str} E50={e50_str} VWAP={vwap_str}"
    
    # Extract position/status info
    position = side_data.get("position")
    pending = side_data.get("pending_entry")
    
    if position:
        entry = position.get("entry_price", 0)
        status = f"TRADE @{entry:.1f}"
    elif pending:
        status = f"PENDING ⊙"
    else:
        status = "FLAT ▲"
    
    return f"{indicators} | {status}"


def _format_side_status(side_data: dict[str, Any]) -> str:
    """Format status for a single side (CE/PE) - compact version.
    
    Returns a short status string like "FLAT ▲" or "TRADE @100.5"
    """
    if not side_data:
        return "FLAT ▲"
    
    position = side_data.get("position")
    pending = side_data.get("pending_entry")
    
    if position:
        qty = position.get("quantity", 1)
        entry = position.get("entry_price", 0)
        return f"TRADE @{entry:.1f}"
    
    if pending:
        signal = pending.get("signal", "?")
        return f"PENDING ⊙"
    
    return "FLAT ▲"


def format_live_status_dashboard(
    timestamp: datetime,
    all_instruments: dict[str, dict[str, Any]]
) -> str:
    """Format the full live status dashboard with all instruments.
    
    Args:
        timestamp: Current timestamp
        all_instruments: Dict mapping instrument name -> (dict mapping strategy -> status)
    
    Returns:
        Complete formatted dashboard as string
    """
    lines = []
    
    # Title with date/time
    lines.append("\n" + "=" * 100)
    lines.append(f"  📊 LIVE TRADING DASHBOARD  |  {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 100)
    lines.append("")
    
    # Display each instrument
    for instrument in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        if instrument in all_instruments:
            lines.append(format_status_table(instrument, all_instruments[instrument]))
            lines.append("")
    


def format_candle_table(
    strategy: str,
    symbol: str,
    side: str,
    datetime_val: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    rsi: Optional[float] = None,
    ema13: Optional[float] = None,
    ema20: Optional[float] = None,
    ema50: Optional[float] = None,
    vwap: Optional[float] = None,
    status_msg: str = "",
) -> str:
    """Format a single candle as a clean table row.
    
    Args:
        strategy: Strategy name (e.g., 'HD', 'CD', 'TC')
        symbol: Trading symbol (e.g., 'NIFTY', 'BANKNIFTY')
        side: Side ('CE' or 'PE')
        datetime_val: Candle timestamp
        open_price: Open price
        high: High price
        low: Low price
        close: Close price
        volume: Trading volume
        rsi: RSI value (optional)
        ema13: EMA13 value (optional)
        ema20: EMA20 value (optional)
        ema50: EMA50 value (optional)
        vwap: VWAP value (optional)
        status_msg: Status message like "LOOKING FOR SETUP" or "IN TRADE"
        
    Returns:
        Formatted table row as string
    """
    ts_str = datetime_val.strftime('%Y-%m-%d %H:%M:%S') if isinstance(datetime_val, datetime) else str(datetime_val)
    rsi_str = f"{rsi:>7.1f}" if rsi is not None else "    N/A"
    ema13_str = f"{ema13:>8.2f}" if ema13 is not None else "     N/A"
    ema20_str = f"{ema20:>8.2f}" if ema20 is not None else "     N/A"
    ema50_str = f"{ema50:>8.2f}" if ema50 is not None else "     N/A"
    vwap_str = f"{vwap:>8.2f}" if vwap is not None else "     N/A"
    status_str = status_msg[:20] if status_msg else "WAITING"
    strategy_str = strategy.upper()[:10]
    row = f"│ {strategy_str:<10} │ {symbol:<12} │ {side:>4} │ {ts_str} │ {open_price:>10.2f} │ {high:>10.2f} │ {low:>10.2f} │ {close:>10.2f} │ {volume:>12} │{rsi_str} │{ema13_str} │{ema20_str} │{ema50_str} │{vwap_str} │ {status_str:<20} │"
    return row


def format_candle_header() -> str:
    """Return a formatted table header for candlestick data."""
    lines = []
    lines.append("┌──────────┬────────────┬──────┬─────────────────────┬────────────┬────────────┬────────────┬────────────┬──────────────┬─────────┬──────────┬──────────┬──────────┬──────────┬────────────┐")
    lines.append("│ Strategy │   Symbol   │ Side │      DateTime       │    Open    │    High    │     Low    │   Close    │    Volume    │   RSI   │  EMA13   │  EMA20   │  EMA50   │   VWAP   │   Status   │")
    lines.append("├──────────┼────────────┼──────┼─────────────────────┼────────────┼────────────┼────────────┼────────────┼──────────────┼─────────┼──────────┼──────────┼──────────┼──────────┼────────────┤")
    return "\n".join(lines)


def format_candle_footer() -> str:
    """Return a formatted table footer for candlestick data."""
    return "└──────────┴────────────┴──────┴─────────────────────┴────────────┴────────────┴────────────┴────────────┴──────────────┴─────────┴──────────┴──────────┴──────────┴──────────┴────────────┘"


def get_status_message(
    side_state: Any,
    side: str,
    rsi: Optional[float] = None,
    ema13: Optional[float] = None,
    ema20: Optional[float] = None,
    ema50: Optional[float] = None,
    close: Optional[float] = None,
) -> str:
    """Get detailed trading status message for a side.
    
    Args:
        side_state: BaseSideState object from engine
        side: 'CE' or 'PE'
        rsi: RSI3 value (optional)
        ema13: EMA13 value (optional)
        ema20: EMA20 value (optional)
        ema50: EMA50 value (optional)
        close: Current close price (optional)
        
    Returns:
        Detailed status message string with all technical info
    """
    
    # Build base status with technical indicators
    ema_info = ""
    rsi_info = ""
    
    if rsi is not None:
        rsi_info = f"RSI={rsi:.1f}"
        if rsi < 20:
            rsi_info += " 🔻"
        elif rsi > 80:
            rsi_info += " 🔺"
    
    if ema13 is not None and ema20 is not None and ema50 is not None:
        ema_info = f"E13={ema13:.1f} E20={ema20:.1f} E50={ema50:.1f}"
    
    # Build state-specific message
    if side_state:
        # IN TRADE - show entry, current, and PnL
        if side_state.position:
            qty = side_state.position.quantity
            entry = side_state.position.entry_price
            pnl = None
            if close is not None:
                pnl = close - entry
            
            if pnl is not None:
                pnl_str = f"(+{pnl:.1f})" if pnl > 0 else f"({pnl:.1f})"
                pnl_emoji = "📈" if pnl > 0 else "📉"
                status = f"IN TRADE Entry={entry:.1f} Curr={close:.1f} {pnl_emoji} {pnl_str}"
            else:
                status = f"IN TRADE Entry={entry:.1f}"
            
            if rsi_info:
                status += f" | {rsi_info}"
            if ema_info:
                status += f" | {ema_info}"
            return status
        
        # PENDING - signal triggered, waiting for entry
        elif side_state.pending_entry:
            signal = side_state.pending_entry.signal.value if hasattr(side_state.pending_entry.signal, 'value') else str(side_state.pending_entry.signal)
            status = f"PENDING ✓ {signal}"
            
            if rsi_info:
                status += f" | {rsi_info}"
            if ema_info:
                status += f" | {ema_info}"
            return status
        
        # LOOKING FOR SETUP
        else:
            status = "LOOKING FOR SETUP"
            if rsi_info:
                status += f" | {rsi_info}"
            if ema_info:
                status += f" | {ema_info}"
            
            # Add setup conditions check
            conditions = []
            if rsi is not None:
                if rsi < 20:
                    conditions.append("RSI oversold 🔻")
                elif rsi > 80:
                    conditions.append("RSI overbought 🔺")
                elif rsi < 30:
                    conditions.append("RSI low")
                elif rsi > 70:
                    conditions.append("RSI high")
            
            if ema13 is not None and ema20 is not None:
                if ema13 > ema20:
                    conditions.append("EMA13>EMA20")
                else:
                    conditions.append("EMA13<EMA20")
            
            if conditions:
                status += f" | {' | '.join(conditions)}"
            
            return status
    
    else:
        # No state
        status = "LOOKING FOR SETUP"
        if rsi_info:
            status += f" | {rsi_info}"
        if ema_info:
            status += f" | {ema_info}"
        return status


def format_candle_data_with_status(
    strategy: str,
    symbol: str,
    side: str,
    row: Any,
    side_state: Any = None,
) -> tuple[str, Optional[float], str]:
    """Extract and format candle data with status.
    
    Args:
        strategy: Strategy name
        symbol: Trading symbol
        side: 'CE' or 'PE'
        row: DataFrame row with OHLC data
        side_state: Engine side state for position/status tracking
        
    Returns:
        Tuple of (formatted_row, rsi_value, status_message)
    """
    ts = row["datetime"]
    ts_obj = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    
    # Safely extract RSI (handle pandas NA values)
    rsi = None
    if "rsi3" in row:
        try:
            rsi_val = row.get("rsi3")
            if rsi_val is not None and pd.notna(rsi_val):
                rsi = float(rsi_val)
        except (TypeError, ValueError):
            rsi = None
    
    # Safely extract EMAs
    ema13 = None
    if "ema13" in row and pd.notna(row.get("ema13")):
        try:
            ema13 = float(row.get("ema13"))
        except (TypeError, ValueError):
            ema13 = None
    
    ema20 = None
    if "ema20" in row and pd.notna(row.get("ema20")):
        try:
            ema20 = float(row.get("ema20"))
        except (TypeError, ValueError):
            ema20 = None
    
    ema50 = None
    if "ema50" in row and pd.notna(row.get("ema50")):
        try:
            ema50 = float(row.get("ema50"))
        except (TypeError, ValueError):
            ema50 = None
    
    vwap = None
    if "vwap" in row and pd.notna(row.get("vwap")):
        try:
            vwap = float(row.get("vwap"))
        except (TypeError, ValueError):
            vwap = None
    
    close = None
    if "close" in row:
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            close = None
    
    status_msg = get_status_message(
        side_state, side,
        rsi=rsi,
        ema13=ema13,
        ema20=ema20,
        ema50=ema50,
        close=close,
    )
    
    candle_row = format_candle_table(
        strategy, symbol, side,
        ts_obj,
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        int(row["volume"]) if "volume" in row else 0,
        rsi=rsi,
        ema13=ema13,
        ema20=ema20,
        ema50=ema50,
        vwap=vwap,
        status_msg=status_msg,
    )
    
    return candle_row, rsi, status_msg


def save_candle_data(
    symbol: str,
    side: str,
    data_rows: list[dict[str, Any]],
    output_dir: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Save candlestick data to both CSV and TXT files in tabular format.
    
    Args:
        symbol: Trading symbol
        side: Side (CE or PE)
        data_rows: List of dicts with keys: datetime, open, high, low, close, volume
        output_dir: Output directory (defaults to logs/candle_data)
        
    Returns:
        Tuple of (csv_path, txt_path) or (None, None) on error
    """
    if not output_dir:
        output_dir = "logs/candle_data"
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    base_name = f"{symbol}_{side}_{datetime.now().strftime('%Y%m%d')}"
    csv_path = output_path / f"{base_name}.csv"
    txt_path = output_path / f"{base_name}.txt"
    
    try:
        # Write CSV
        with open(csv_path, 'w', newline='') as f:
            fieldnames = ['DateTime', 'Strategy', 'Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'Status']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in data_rows:
                writer.writerow({
                    'DateTime': row.get('datetime', ''),
                    'Strategy': row.get('strategy', 'N/A'),
                    'Open': row.get('open', 0),
                    'High': row.get('high', 0),
                    'Low': row.get('low', 0),
                    'Close': row.get('close', 0),
                    'Volume': row.get('volume', 0),
                    'RSI': row.get('rsi', ''),
                    'Status': row.get('status', ''),
                })
        
        # Write TXT with tabular format
        with open(txt_path, 'w') as f:
            f.write(f"Candlestick Data: {symbol} {side}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Candles: {len(data_rows)}\n")
            f.write("\n")
            f.write(format_candle_header() + "\n")
            for row in data_rows:
                dt = row.get('datetime', '')
                if isinstance(dt, str):
                    ts_str = dt
                else:
                    ts_str = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                
                strategy = row.get('strategy', 'N/A')[:10]
                rsi = row.get('rsi')
                rsi_str = f"{rsi:>7.1f}" if rsi is not None else "    N/A"
                status = row.get('status', 'WAITING')[:24]
                
                line = f"│ {strategy:<10} │ {symbol:<12} │ {side:>4} │ {ts_str} │ {float(row.get('open', 0)):>10.2f} │ {float(row.get('high', 0)):>10.2f} │ {float(row.get('low', 0)):>10.2f} │ {float(row.get('close', 0)):>10.2f} │ {int(row.get('volume', 0)):>12} │{rsi_str} │ {status:<24} │\n"
                f.write(line)
            f.write(format_candle_footer() + "\n")
        
        return str(csv_path), str(txt_path)
    except Exception as e:
        print(f"Error saving candle data: {e}")
        return None, None


def save_consolidated_candle(symbol: str, side: str, candle: dict[str, Any]) -> str:
    """Save a single candle to consolidated daily CSV file in logs/ directory.
    
    The file format is: logs/SYMBOL_SIDE_YYYYMMDD.csv
    All candles from market open to close are appended to this file.
    
    Args:
        symbol: Trading symbol (e.g., NIFTY)
        side: Side (CE or PE)
        candle: Dict with keys: datetime, open, high, low, close, volume, strategy, rsi, status
        
    Returns:
        Path to the CSV file
    """
    today = datetime.now().strftime('%Y%m%d')
    filename = f"{symbol}_{side}_{today}.csv"
    filepath = Path("logs") / filename
    
    # Create logs directory if needed
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file exists (to determine if we need to write headers)
    file_exists = filepath.exists()
    
    try:
        with open(filepath, 'a', newline='') as f:
            fieldnames = ['DateTime', 'Strategy', 'Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'Status']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Write header only if file is new
            if not file_exists:
                writer.writeheader()
            
            # Write the candle data
            dt = candle.get('datetime', '')
            if hasattr(dt, 'strftime'):
                dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                dt_str = str(dt)
            
            writer.writerow({
                'DateTime': dt_str,
                'Strategy': candle.get('strategy', ''),
                'Open': f"{float(candle.get('open', 0)):.2f}",
                'High': f"{float(candle.get('high', 0)):.2f}",
                'Low': f"{float(candle.get('low', 0)):.2f}",
                'Close': f"{float(candle.get('close', 0)):.2f}",
                'Volume': int(candle.get('volume', 0)),
                'RSI': f"{float(candle.get('rsi', 0)):.1f}" if candle.get('rsi') else '',
                'Status': candle.get('status', ''),
            })
        
        return str(filepath)
    except Exception as e:
        print(f"Error saving consolidated candle: {e}")
        return ""


def export_all_candles_to_csv(
    all_candles: dict[str, dict[str, list[dict]]],
    output_dir: str = "logs"
) -> dict[str, str]:
    """Export all accumulated candles to consolidated CSV files by symbol and side.
    
    Args:
        all_candles: Dict structure: {symbol: {side: [candle_dicts]}}
                    Each candle dict has: datetime, open, high, low, close, volume, strategy, rsi, status
        output_dir: Output directory (defaults to "logs")
        
    Returns:
        Dict mapping "SYMBOL_SIDE" -> file_path
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime('%Y%m%d')
    files_created = {}
    
    try:
        for symbol, sides_data in all_candles.items():
            for side, candles in sides_data.items():
                if not candles:
                    continue
                
                filename = f"{symbol}_{side}_{today}.csv"
                filepath = output_path / filename
                key = f"{symbol}_{side}"
                
                # Write CSV
                with open(filepath, 'w', newline='') as f:
                    fieldnames = ['DateTime', 'Strategy', 'Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'Status']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for candle in candles:
                        dt = candle.get('datetime', '')
                        if hasattr(dt, 'strftime'):
                            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            dt_str = str(dt)
                        
                        writer.writerow({
                            'DateTime': dt_str,
                            'Strategy': candle.get('strategy', ''),
                            'Open': f"{float(candle.get('open', 0)):.2f}",
                            'High': f"{float(candle.get('high', 0)):.2f}",
                            'Low': f"{float(candle.get('low', 0)):.2f}",
                            'Close': f"{float(candle.get('close', 0)):.2f}",
                            'Volume': int(candle.get('volume', 0)),
                            'RSI': f"{float(candle.get('rsi', 0)):.1f}" if candle.get('rsi') else '',
                            'Status': candle.get('status', ''),
                        })
                
                files_created[key] = str(filepath)
                print(f"✅ Exported {len(candles)} candles to {filename}")
        
        return files_created
    except Exception as e:
        print(f"Error exporting candles: {e}")
        return {}


def export_all_candles_to_single_csv(
    all_candles: dict[str, dict[str, list[dict]]],
    output_dir: str = "logs",
    filename: str = "trading_log"
) -> str:
    """Export ALL candles (all symbols, all sides) to a SINGLE consolidated CSV file.
    
    Args:
        all_candles: Dict structure: {symbol: {side: [candle_dicts]}}
        output_dir: Output directory (defaults to "logs")
        filename: Base filename without extension (defaults to "trading_log")
        
    Returns:
        Path to the single CSV file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime('%Y%m%d')
    filepath = output_path / f"{filename}_{today}.csv"
    
    try:
        # Collect all candles across all symbols and sides
        all_data = []
        
        for symbol in sorted(all_candles.keys()):
            for side in ["CE", "PE"]:
                candles = all_candles.get(symbol, {}).get(side, [])
                for candle in candles:
                    all_data.append({
                        'Symbol': symbol,
                        'Side': side,
                        'DateTime': candle.get('datetime', ''),
                        'Strategy': candle.get('strategy', ''),
                        'Open': f"{float(candle.get('open', 0)):.2f}",
                        'High': f"{float(candle.get('high', 0)):.2f}",
                        'Low': f"{float(candle.get('low', 0)):.2f}",
                        'Close': f"{float(candle.get('close', 0)):.2f}",
                        'Volume': int(candle.get('volume', 0)),
                        'RSI': f"{float(candle.get('rsi', 0)):.1f}" if candle.get('rsi') else '',
                        'ema13': candle.get('ema13'),
                        'ema20': candle.get('ema20'),
                        'ema50': candle.get('ema50'),
                        'vwap': candle.get('vwap'),
                        'Status': candle.get('status', ''),
                    })
        
        # Sort by DateTime
        all_data.sort(key=lambda x: x['DateTime'])
        
        # Write single CSV file
        with open(filepath, 'w', newline='') as f:
            if all_data:
                fieldnames = ['Symbol', 'Side', 'DateTime', 'Strategy', 'Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'EMA13', 'EMA20', 'EMA50', 'VWAP', 'Status']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in all_data:
                    dt = row['DateTime']
                    if hasattr(dt, 'strftime'):
                        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        dt_str = str(dt)
                    
                    writer.writerow({
                        'Symbol': row['Symbol'],
                        'Side': row['Side'],
                        'DateTime': dt_str,
                        'Strategy': row['Strategy'],
                        'Open': row['Open'],
                        'High': row['High'],
                        'Low': row['Low'],
                        'Close': row['Close'],
                        'Volume': row['Volume'],
                        'RSI': row['RSI'],
                        'EMA13': f"{float(row.get('ema13', 0)):.2f}" if row.get('ema13') else '',
                        'EMA20': f"{float(row.get('ema20', 0)):.2f}" if row.get('ema20') else '',
                        'EMA50': f"{float(row.get('ema50', 0)):.2f}" if row.get('ema50') else '',
                        'VWAP': f"{float(row.get('vwap', 0)):.2f}" if row.get('vwap') else '',
                        'Status': row['Status'],
                    })
        
        total_candles = len(all_data)
        print(f"✅ Exported {total_candles} candles to {filepath}")
        return str(filepath)
        
    except Exception as e:
        print(f"Error exporting to single CSV: {e}")
        return ""
