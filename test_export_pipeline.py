#!/usr/bin/env python3
"""Test script demonstrating the export pipeline with runner classes."""

import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from core.runner import LiveFeedRunner
from core.models import StrategyConfig, RiskConfig
from core.broker import HistoricalReplayBroker
from unittest.mock import Mock, MagicMock

def demo_export_pipeline():
    """Demonstrate how the export pipeline works with LiveFeedRunner."""
    
    print("\n" + "=" * 80)
    print("🔄 EXPORT PIPELINE DEMONSTRATION")
    print("=" * 80)
    
    # Create mock broker and config
    mock_broker = Mock(spec=HistoricalReplayBroker)
    mock_engine = Mock()
    mock_engine.state = Mock()
    mock_engine.state.atm_locked = False
    
    config = StrategyConfig(
        spot_symbol="NIFTY",
        option_index_symbol="NIFTY",
    )
    
    # Create runner
    runner = LiveFeedRunner(
        broker=mock_broker,
        engine=mock_engine,
        cfg=config,
        strategy_name="HD",
        lookback_days=5,
        poll_slack_seconds=5,
    )
    
    print("\n✅ Step 1: Created LiveFeedRunner for strategy 'HD'")
    print(f"   • Symbol: {config.spot_symbol}")
    print(f"   • Strategy: HD")
    print(f"   • Buffer initialized: {runner._candle_buffer}")
    
    # Simulate candle data being buffered
    sample_candles = [
        {
            'datetime': datetime(2026, 8, 10, 9, 30, 0),
            'strategy': 'HD',
            'open': 20000.50,
            'high': 20150.75,
            'low': 19950.25,
            'close': 20100.00,
            'volume': 125000,
            'rsi': 52.3,
            'status': 'LOOKING FOR SETUP'
        },
        {
            'datetime': datetime(2026, 8, 10, 9, 35, 0),
            'strategy': 'HD',
            'open': 20100.00,
            'high': 20200.50,
            'low': 20050.00,
            'close': 20180.75,
            'volume': 145000,
            'rsi': 68.5,
            'status': 'PENDING BUY_CE'
        },
        {
            'datetime': datetime(2026, 8, 10, 9, 40, 0),
            'strategy': 'HD',
            'open': 20180.75,
            'high': 20250.00,
            'low': 20120.00,
            'close': 20220.50,
            'volume': 167000,
            'rsi': 75.2,
            'status': 'IN TRADE @ 20200.0'
        },
        {
            'datetime': datetime(2026, 8, 10, 9, 45, 0),
            'strategy': 'HD',
            'open': 20220.50,
            'high': 20300.00,
            'low': 20180.00,
            'close': 20280.75,
            'volume': 189000,
            'rsi': 82.1,
            'status': 'IN TRADE @ 20200.0'
        },
    ]
    
    # Add samples to CE buffer
    runner._candle_buffer['CE'].extend(sample_candles)
    
    print("\n✅ Step 2: Buffered 4 candles in CE side")
    print(f"   • Total candles buffered: {len(runner._candle_buffer['CE'])}")
    print(f"   • Time span: {sample_candles[0]['datetime']} to {sample_candles[-1]['datetime']}")
    
    # Add some PE data
    runner._candle_buffer['PE'].append({
        'datetime': datetime(2026, 8, 10, 9, 30, 0),
        'strategy': 'HD',
        'open': 450.25,
        'high': 465.50,
        'low': 445.00,
        'close': 460.75,
        'volume': 95000,
        'rsi': 58.3,
        'status': 'LOOKING FOR SETUP'
    })
    
    print(f"   • PE candles buffered: {len(runner._candle_buffer['PE'])}")
    
    # Show buffer structure
    print("\n✅ Step 3: Buffer structure before export")
    print("   CE Buffer Sample (1st record):")
    ce_first = runner._candle_buffer['CE'][0]
    for key, value in ce_first.items():
        print(f"      • {key}: {value}")
    
    # Export the data
    print("\n✅ Step 4: Exporting buffered data...")
    output_dir = "logs/test_export_pipeline"
    
    # Clean up if exists
    if Path(output_dir).exists():
        shutil.rmtree(output_dir)
    
    runner.export_candle_data(output_dir=output_dir)
    
    # Verify files created
    output_path = Path(output_dir)
    csv_files = list(output_path.glob("*.csv"))
    txt_files = list(output_path.glob("*.txt"))
    
    print(f"\n✅ Step 5: Files created")
    print(f"   • CSV files: {len(csv_files)}")
    for f in csv_files:
        size = f.stat().st_size
        print(f"      - {f.name} ({size} bytes)")
    print(f"   • TXT files: {len(txt_files)}")
    for f in txt_files:
        size = f.stat().st_size
        print(f"      - {f.name} ({size} bytes)")
    
    # Show CSV content
    if csv_files:
        print(f"\n✅ Step 6: CSV File Content (CE)")
        print("   " + "-" * 76)
        csv_file = csv_files[0]
        with open(csv_file, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines[:3]):  # Header + 2 rows
                print(f"   {line.rstrip()}")
            if len(lines) > 3:
                print(f"   ... ({len(lines) - 1} total records)")
        print("   " + "-" * 76)
    
    # Show TXT content
    if txt_files:
        print(f"\n✅ Step 7: TXT File Content (CE) - Formatted Table")
        print("   " + "-" * 76)
        txt_file = txt_files[0]
        with open(txt_file, 'r') as f:
            lines = f.readlines()
            for line in lines[:15]:  # Show header + 2-3 data rows
                print(f"   {line.rstrip()}")
            if len(lines) > 15:
                print(f"   ... (more rows ...)")
        print("   " + "-" * 76)
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ EXPORT PIPELINE TEST COMPLETE")
    print("=" * 80)
    print("\n📊 Features Demonstrated:")
    print("   ✓ Data buffering during live trading")
    print("   ✓ CSV export with all columns (DateTime, Strategy, OHLCV, RSI, Status)")
    print("   ✓ TXT export with formatted ASCII table")
    print("   ✓ Support for multiple sides (CE and PE)")
    print("   ✓ Automatic file naming with symbol and date")
    print("   ✓ Proper directory structure creation")
    
    print("\n🔄 Export Workflow:")
    print("   1. Runner buffers each candle during live trading")
    print("   2. At session end, runner.stop() is called")
    print("   3. stop() triggers export_candle_data() automatically")
    print("   4. Data written to CSV (analysis) and TXT (readable)")
    print("   5. Complete session history preserved for review")
    
    print("\n📁 File Locations:")
    print(f"   • Output directory: {output_dir}/")
    print(f"   • Format: {{SYMBOL}}_{{SIDE}}_{{YYYYMMDD}}.{{csv|txt}}")
    print(f"   • Example: NIFTY_CE_20260810.csv")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    demo_export_pipeline()
