#!/usr/bin/env python3
"""
Demo: Single Consolidated CSV Export

Shows how all candles from all symbols and sides are saved to ONE CSV file
with format: trading_log_YYYYMMDD.csv
"""

from datetime import datetime, timedelta
from core.display import export_all_candles_to_single_csv

def generate_sample_candles():
    """Generate sample candles for multiple symbols and sides."""
    
    all_candles = {}
    
    symbols = ["NIFTY", "BANKNIFTY", "SENSEX"]
    
    for symbol in symbols:
        all_candles[symbol] = {"CE": [], "PE": []}
        
        base_price = 100 if symbol == "NIFTY" else 200
        
        for side in ["CE", "PE"]:
            times = [
                "09:23", "09:26", "09:29", "10:12", "10:15",
                "10:18", "10:21", "14:30", "15:00", "15:12"
            ]
            
            for i, time_str in enumerate(times):
                hour, minute = map(int, time_str.split(':'))
                candle_time = datetime(2026, 8, 10, hour, minute)
                
                price_offset = 0.95 if side == "PE" else 1.0
                base = base_price * price_offset + (i * 1.5)
                
                all_candles[symbol][side].append({
                    'datetime': candle_time,
                    'strategy': 'TC' if i < 5 else 'HD',
                    'open': base,
                    'high': base + 3.5,
                    'low': base - 1.5,
                    'close': base + 2.0,
                    'volume': 1000000 + (i * 100000),
                    'rsi': 50 + (i % 3) * 20,
                    'ema13': base + 0.5,
                    'ema20': base - 0.5,
                    'ema50': base - 1.5,
                    'vwap': base,
                    'status': 'LOOKING FOR SETUP' if i < 3 else ('PENDING' if i < 6 else 'IN TRADE')
                })
    
    return all_candles


def main():
    print("\n" + "="*90)
    print("  🎯 SINGLE CONSOLIDATED CSV EXPORT DEMO")
    print("="*90)
    print()
    
    # Generate sample data for multiple symbols
    print("📊 Generating sample candles for NIFTY, BANKNIFTY, SENSEX (CE + PE)...")
    all_candles = generate_sample_candles()
    
    total_candles = sum(len(sides[side]) for symbol, sides in all_candles.items() for side in ["CE", "PE"])
    print(f"   ✓ Generated {total_candles} candles across all symbols and sides")
    print()
    
    # Show breakdown
    print("📈 Candle Breakdown:")
    for symbol in sorted(all_candles.keys()):
        ce_count = len(all_candles[symbol]["CE"])
        pe_count = len(all_candles[symbol]["PE"])
        print(f"   • {symbol}: {ce_count} CE + {pe_count} PE = {ce_count + pe_count} total")
    print()
    
    print("📁 Exporting ALL data to ONE file in logs/ directory...")
    print()
    
    # Export to SINGLE file
    filepath = export_all_candles_to_single_csv(all_candles, output_dir='logs', filename='trading_log')
    
    print()
    print("✅ Export Complete!")
    print()
    print(f"   📄 File: trading_log_20260810.csv")
    print(f"   📍 Location: {filepath}")
    print()
    
    # Show sample content
    print("📋 Preview of first few rows:")
    print("-" * 150)
    import csv
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i < 5:  # First 5 rows
                print(f"  {row['Symbol']:<12} | {row['Side']:<4} | {row['DateTime']:<19} | {row['Strategy']:<8} | "
                      f"C={row['Close']:>8} | RSI={row['RSI']:>6} | EMA13={row['EMA13']:>7} | EMA20={row['EMA20']:>7} | "
                      f"VWAP={row['VWAP']:>7} | {row['Status']:<20}")
            elif i == 5:
                print("  ... (more rows) ...")
    print("-" * 120)
    print()
    
    print("🎯 Key Features:")
    print("   ✓ ONE file: trading_log_YYYYMMDD.csv")
    print("   ✓ ALL symbols: NIFTY, BANKNIFTY, SENSEX")
    print("   ✓ ALL sides: CE and PE combined")
    print("   ✓ COMPLETE session: 9:20 AM to 3:15 PM IST")
    print("   ✓ Rich metadata: Strategy, RSI, Status for each candle")
    print("   ✓ Sorted by DateTime: Easy to analyze chronologically")
    print()
    
    print("📊 File Format - 15 Columns:")
    print("   1. Symbol (NIFTY, BANKNIFTY, SENSEX)")
    print("   2. Side (CE or PE)")
    print("   3. DateTime (YYYY-MM-DD HH:MM:SS)")
    print("   4. Strategy (TC, HD, CD)")
    print("   5. Open (Price)")
    print("   6. High (Price)")
    print("   7. Low (Price)")
    print("   8. Close (Price)")
    print("   9. Volume (Trading Volume)")
    print("   10. RSI (RSI3 Indicator)")
    print("   11. EMA13 (13-period Exponential Moving Average) ⭐ NEW")
    print("   12. EMA20 (20-period Exponential Moving Average) ⭐ NEW")
    print("   13. EMA50 (50-period Exponential Moving Average) ⭐ NEW")
    print("   14. VWAP (Volume Weighted Average Price) ⭐ NEW")
    print("   15. Status (LOOKING FOR SETUP, PENDING, IN TRADE, etc.)")
    print()
    print("="*90)


if __name__ == "__main__":
    main()
