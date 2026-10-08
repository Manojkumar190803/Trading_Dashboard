#!/usr/bin/env python3
"""Test mode detection and data fetching from OpenAlgo"""

import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv()

sys.path.insert(0, str(Path.cwd()))
from core.dashboard_data import DashboardDataProvider

api_key = os.getenv("OPENALGO_API_KEY", "demo")
host = os.getenv("OPENALGO_HOST", "http://localhost:5002")

print("=" * 70)
print("TESTING MODE DETECTION & DATA FETCH FROM OPENALGO")
print("=" * 70)

print(f"\n1. CONFIGURATION:")
print(f"   OPENALGO_MODE from .env: {os.getenv('OPENALGO_MODE')}")
print(f"   OPENALGO_API_KEY: {api_key[:20]}...")
print(f"   OPENALGO_HOST: {host}")

provider = DashboardDataProvider(api_key=api_key, host=host)

print(f"\n2. MODE DETECTION:")
detected_mode = provider._detect_mode()
print(f"   Detected mode: {detected_mode}")
print(f"   ✓ Mode should be: LIVE")

print(f"\n3. ENGINE STATUS:")
engine_status = provider._check_engine_status()
print(f"   Engine status: {engine_status}")

print(f"\n4. FETCHING ACCOUNT DATA:")
try:
    positions = provider._fetch_positions()
    print(f"   ✓ Positions fetched: {len(positions)} positions")
    if positions:
        print(f"     First position: {positions[0].get('symbol', 'N/A')}")
except Exception as e:
    print(f"   ✗ Error fetching positions: {e}")

try:
    orders = provider._fetch_orders()
    print(f"   ✓ Orders fetched: {len(orders)} orders")
except Exception as e:
    print(f"   ✗ Error fetching orders: {e}")

try:
    account_info = provider._fetch_account_info()
    print(f"   ✓ Account info fetched:")
    print(f"     - Available Margin: {account_info.get('availableMargin', 'N/A')}")
    print(f"     - MTM: {account_info.get('mtm', 'N/A')}")
    print(f"     - Used Margin: {account_info.get('used_margin', 'N/A')}")
    print(f"\n   Raw account data keys: {list(account_info.keys())}")
except Exception as e:
    print(f"   ✗ Error fetching account info: {e}")

print(f"\n5. FULL ACCOUNT SUMMARY:")
data = provider.get_account_summary()
print(f"   Mode in data: {data.get('mode')}")
print(f"   Engine status in data: {data.get('engine_status')}")
print(f"   Positions in data: {len(data.get('positions', []))}")

print(f"\n6. WRITING DASHBOARD DATA TO FILE:")
provider.write_dashboard_json()
print(f"   ✓ Dashboard data written to logs/dashboard_data.json")

# Read back and verify
with open("logs/dashboard_data.json") as f:
    file_data = json.load(f)
    print(f"\n7. VERIFYING FILE CONTENTS:")
    print(f"   Mode in file: {file_data.get('mode')}")
    print(f"   Engine status in file: {file_data.get('engine_status')}")
    print(f"   Account available margin: {file_data.get('account', {}).get('availableMargin', 'N/A')}")
    print(f"   Account MTM: {file_data.get('account', {}).get('mtm', 'N/A')}")

print("\n" + "=" * 70)
print("✓ TEST COMPLETE")
print("=" * 70)
