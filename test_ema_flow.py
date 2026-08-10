#!/usr/bin/env python3
"""
Test script to trace EMA values through the complete data flow.
Simulates: Data fetch → Add indicators → Buffer → Display
"""

import pandas as pd
from datetime import datetime, timedelta
from core.indicators import add_indicators
from core.models import StrategyConfig
from core.display import format_candle_data_with_status

def simulate_broker_data():
    """Simulate data as it would come from OpenAlgo broker."""
    dates = pd.date_range(datetime.now() - timedelta(hours=2), periods=40, freq='3min')
    return pd.DataFrame({
        'datetime': dates,
        'open': [100 + i*0.3 for i in range(40)],
        'high': [102 + i*0.3 for i in range(40)],
        'low': [98 + i*0.3 for i in range(40)],
        'close': [101 + i*0.3 for i in range(40)],
        'volume': [1000000]*40,
    })

def simulate_runner_flow():
    """Simulate the exact flow as in LiveFeedRunner._fetch_option_history()"""
    print("\n" + "="*100)
    print("  STEP-BY-STEP DATA FLOW - EMA TRACKING")
    print("="*100 + "\n")
    
    # STEP 1: Fetch from broker
    print("📍 STEP 1: Fetch data from broker")
    raw_data = simulate_broker_data()
    print(f"   Columns received: {raw_data.columns.tolist()}")
    print(f"   Rows: {len(raw_data)}")
    print(f"   Has EMA? {any('ema' in col.lower() for col in raw_data.columns)}")
    print()
    
    # STEP 2: Normalize
    print("📍 STEP 2: Normalize data (_normalize_history_df)")
    normalized = raw_data.copy()  # In real code, there's normalization
    print(f"   After normalize: {normalized.columns.tolist()}")
    print()
    
    # STEP 3: Add indicators (THIS IS KEY)
    print("📍 STEP 3: Add technical indicators (add_indicators)")
    cfg = StrategyConfig()
    with_indicators = add_indicators(normalized.reset_index(drop=True), cfg)
    print(f"   After add_indicators: {with_indicators.columns.tolist()}")
    print(f"   Has EMA? {any('ema' in col.lower() for col in with_indicators.columns)}")
    ema_cols = ['ema13', 'ema20', 'ema50', 'rsi3', 'vwap']
    for col in ema_cols:
        if col in with_indicators.columns:
            val = with_indicators.iloc[-1][col]
            print(f"   ✅ {col}: {val}")
        else:
            print(f"   ❌ {col}: MISSING")
    print()
    
    # STEP 4: Filter by market hours
    print("📍 STEP 4: Filter by market hours")
    today = datetime.now().date()
    session_start = datetime.combine(today, datetime.min.time().replace(hour=9, minute=20))
    session_end = datetime.combine(today, datetime.min.time().replace(hour=15, minute=15))
    filtered = with_indicators[
        (with_indicators["datetime"] >= session_start) & 
        (with_indicators["datetime"] < session_end)
    ]
    print(f"   Before filter: {len(with_indicators)} rows")
    print(f"   After filter: {len(filtered)} rows")
    print(f"   Indicators still present? {any('ema13' in col for col in filtered.columns)}")
    print()
    
    # STEP 5: Extract to display (THIS IS WHERE DATA IS DISPLAYED)
    print("📍 STEP 5: Extract and format for display (format_candle_data_with_status)")
    if len(filtered) > 0:
        last_row = filtered.iloc[-1]
        print(f"   Sample row data:")
        print(f"   - datetime: {last_row['datetime']}")
        print(f"   - close: {last_row['close']}")
        print(f"   - ema13: {last_row.get('ema13', 'MISSING')}")
        print(f"   - ema20: {last_row.get('ema20', 'MISSING')}")
        print(f"   - ema50: {last_row.get('ema50', 'MISSING')}")
        print(f"   - rsi3: {last_row.get('rsi3', 'MISSING')}")
        print(f"   - vwap: {last_row.get('vwap', 'MISSING')}")
        print()
        
        # Actually format it
        candle_row, rsi_val, status = format_candle_data_with_status(
            strategy="TC",
            symbol="NIFTY",
            side="CE",
            row=last_row,
            side_state=None
        )
        print(f"   Formatted output:")
        print(f"   {candle_row}")
        print()
    
    # STEP 6: Check candle buffer (CSV export path)
    print("📍 STEP 6: What gets saved to candle buffer (CSV export)")
    if len(filtered) > 0:
        sample_row = filtered.iloc[-1]
        
        # Safely extract values (same logic as in runner.py)
        rsi_val = None
        if "rsi3" in sample_row and pd.notna(sample_row.get("rsi3")):
            try:
                rsi_val = float(sample_row.get("rsi3"))
            except (TypeError, ValueError):
                rsi_val = None
        
        ema13_val = None
        if "ema13" in sample_row and pd.notna(sample_row.get("ema13")):
            try:
                ema13_val = float(sample_row.get("ema13"))
            except (TypeError, ValueError):
                ema13_val = None
        
        ema20_val = None
        if "ema20" in sample_row and pd.notna(sample_row.get("ema20")):
            try:
                ema20_val = float(sample_row.get("ema20"))
            except (TypeError, ValueError):
                ema20_val = None
        
        ema50_val = None
        if "ema50" in sample_row and pd.notna(sample_row.get("ema50")):
            try:
                ema50_val = float(sample_row.get("ema50"))
            except (TypeError, ValueError):
                ema50_val = None
        
        vwap_val = None
        if "vwap" in sample_row and pd.notna(sample_row.get("vwap")):
            try:
                vwap_val = float(sample_row.get("vwap"))
            except (TypeError, ValueError):
                vwap_val = None
        
        buffer_entry = {
            "datetime": sample_row["datetime"],
            "strategy": "TC",
            "open": float(sample_row["open"]),
            "high": float(sample_row["high"]),
            "low": float(sample_row["low"]),
            "close": float(sample_row["close"]),
            "volume": int(sample_row["volume"]),
            "rsi": rsi_val,
            "ema13": ema13_val,
            "ema20": ema20_val,
            "ema50": ema50_val,
            "vwap": vwap_val,
            "status": "TEST",
        }
        print(f"   Buffer entry created:")
        for key, val in buffer_entry.items():
            if key in ['ema13', 'ema20', 'ema50', 'rsi', 'vwap']:
                emoji = "✅" if val is not None else "❌"
                print(f"   {emoji} {key}: {val}")
    print()
    
    print("="*100)
    print("  SUMMARY")
    print("="*100)
    print("""
If all steps show ✅:
  → EMAs are being calculated, extracted, and displayed correctly
  → Issue might be instrument-specific or environment-specific

If any step shows ❌:
  → That's where the EMA data is being lost
  → Need to investigate that specific step

Common issues:
  1. Step 3: If add_indicators() not working → Check core/indicators.py
  2. Step 4: If filtering removes data → Check market hours settings
  3. Step 5: If row doesn't have EMA → Data flow broken before display
  4. Step 6: If buffer entry has None → CSV export affected
""")
    print("="*100 + "\n")

if __name__ == "__main__":
    simulate_runner_flow()
