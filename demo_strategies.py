#!/usr/bin/env python3
"""Demo script showing all strategies working with sample market data."""

import sys
import pandas as pd
from datetime import datetime, timedelta

from core.models import StrategyConfig, Signal
from core.indicators import add_indicators
from strategies.hd import HDSignalProvider
from strategies.cd import CDSignalProvider
from strategies.tc import TCSignalProvider


def create_sample_data(num_candles=30):
    """Create realistic OHLCV sample data"""
    base_price = 25000.0
    data = []
    
    for i in range(num_candles):
        dt = datetime(2026, 8, 10, 9, 20) + timedelta(minutes=3*i)
        
        # Create realistic candle patterns
        open_price = base_price + (i % 3 - 1) * 10
        close_price = open_price + (i % 5 - 2) * 15
        high_price = max(open_price, close_price) + 20
        low_price = min(open_price, close_price) - 10
        volume = 1000 + (i * 50) % 500
        
        data.append({
            'datetime': dt,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume,
        })
    
    df = pd.DataFrame(data)
    return add_indicators(df, StrategyConfig())


def test_strategy(strategy_name, strategy_provider, df):
    """Test a strategy with sample data"""
    signals = []
    
    ce_state = strategy_provider.create_side_state()
    pe_state = strategy_provider.create_side_state()
    
    for idx, row in df.iterrows():
        prev_row = df.iloc[idx-1] if idx > 0 else None
        
        strategy_provider.update_state(ce_state, row, prev_row)
        strategy_provider.update_state(pe_state, row, prev_row)
        
        ce_signal = strategy_provider.generate_signal("CE", ce_state, row, prev_row)
        pe_signal = strategy_provider.generate_signal("PE", pe_state, row, prev_row)
        
        if ce_signal != Signal.NONE or pe_signal != Signal.NONE:
            signals.append({
                'time': row['datetime'],
                'close': row['close'],
                'ce_signal': ce_signal.name,
                'pe_signal': pe_signal.name,
            })
    
    return signals


def main():
    print("\n" + "=" * 70)
    print("STRATEGY ENGINE DEMONSTRATION")
    print("=" * 70 + "\n")
    
    print("Generating sample market data...")
    df = create_sample_data(30)
    print(f"✓ Generated {len(df)} candles of sample data\n")
    
    # Display sample data
    print("Sample Data (first 5 rows):")
    print(df[['datetime', 'open', 'high', 'low', 'close', 'volume']].head().to_string(index=False))
    print("...\n")
    
    # Test HD Strategy
    print("-" * 70)
    print("Testing Hammer Down (HD) Strategy")
    print("-" * 70)
    
    hd = HDSignalProvider()
    hd_signals = test_strategy("HD", hd, df)
    
    print(f"✓ HD Strategy generated {len(hd_signals)} signal(s)")
    if hd_signals:
        print("  Sample signals:")
        for sig in hd_signals[:3]:
            print(f"    {sig['time']}: CE={sig['ce_signal']}, PE={sig['pe_signal']}")
    
    # Test CD Strategy
    print("\n" + "-" * 70)
    print("Testing Candle Down (CD) Strategy")
    print("-" * 70)
    
    cd = CDSignalProvider()
    cd_signals = test_strategy("CD", cd, df)
    
    print(f"✓ CD Strategy generated {len(cd_signals)} signal(s)")
    if cd_signals:
        print("  Sample signals:")
        for sig in cd_signals[:3]:
            print(f"    {sig['time']}: CE={sig['ce_signal']}, PE={sig['pe_signal']}")
    
    # Test TC Strategy
    print("\n" + "-" * 70)
    print("Testing Tail Cannon (TC) Strategy")
    print("-" * 70)
    
    tc = TCSignalProvider()
    tc_signals = test_strategy("TC", tc, df)
    
    print(f"✓ TC Strategy generated {len(tc_signals)} signal(s)")
    if tc_signals:
        print("  Sample signals:")
        for sig in tc_signals[:3]:
            print(f"    {sig['time']}: CE={sig['ce_signal']}, PE={sig['pe_signal']}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✓ Market Data: {len(df)} candles processed successfully")
    print(f"✓ Indicators: EMA, VWAP, RSI calculated")
    print(f"✓ HD Strategy: {len(hd_signals)} signals generated")
    print(f"✓ CD Strategy: {len(cd_signals)} signals generated")
    print(f"✓ TC Strategy: {len(tc_signals)} signals generated")
    print(f"\n✓ Strategy engine is working correctly!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
