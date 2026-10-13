#!/usr/bin/env python3
"""Test OpenAlgo connectivity from Streamlit container perspective."""

import os
import sys
import json
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_streamlit_openalgo_connection():
    """Test if Streamlit container can connect to OpenAlgo."""
    print("=" * 70)
    print("🧪 Testing OpenAlgo Connectivity for Streamlit Dashboard")
    print("=" * 70)
    print()

    # Step 1: Check environment variables
    print("1️⃣  Checking environment variables:")
    api_key = os.getenv("OPENALGO_API_KEY", "")
    host = os.getenv("OPENALGO_HOST", os.getenv("OPENALGO_BASE_URL", "http://127.0.0.1:5002"))
    
    print(f"   ✓ OPENALGO_HOST: {host}")
    if api_key:
        print(f"   ✓ OPENALGO_API_KEY: {api_key[:20]}...{api_key[-4:]}")
    else:
        print("   ✗ OPENALGO_API_KEY: NOT SET")
        return False
    print()

    # Step 2: Try importing openalgo
    print("2️⃣  Testing OpenAlgo library import:")
    try:
        from openalgo import api as openalgo_api
        print("   ✓ openalgo library imported successfully")
    except ImportError as e:
        print(f"   ✗ Failed to import openalgo: {e}")
        return False
    print()

    # Step 3: Test connection to OpenAlgo
    print("3️⃣  Testing connection to OpenAlgo API:")
    try:
        client = openalgo_api(api_key=api_key, host=host)
        print(f"   ✓ OpenAlgo client created successfully")
        print(f"      Host: {host}")
        print(f"      Client type: {type(client).__name__}")
    except Exception as e:
        print(f"   ✗ Failed to create OpenAlgo client: {e}")
        return False
    print()

    # Step 4: Test fetching funds
    print("4️⃣  Testing funds() API call:")
    try:
        funds_response = client.funds()
        print(f"   ✓ funds() call successful")
        if isinstance(funds_response, dict):
            if "status" in funds_response:
                print(f"      Status: {funds_response.get('status')}")
            if "data" in funds_response:
                funds_data = funds_response.get("data", {})
                print(f"      Available Margin: {funds_data.get('availableMargin', 'N/A')}")
            print(f"      Response size: {len(json.dumps(funds_response))} bytes")
    except Exception as e:
        print(f"   ✗ Failed to fetch funds: {e}")
        return False
    print()

    # Step 5: Test fetching positions
    print("5️⃣  Testing positionbook() API call:")
    try:
        positions_response = client.positionbook()
        print(f"   ✓ positionbook() call successful")
        if isinstance(positions_response, dict):
            if "status" in positions_response:
                print(f"      Status: {positions_response.get('status')}")
            if "data" in positions_response:
                positions = positions_response.get("data", [])
                print(f"      Positions found: {len(positions)}")
                if positions:
                    first_pos = positions[0]
                    print(f"      First position: {first_pos.get('symbol', 'N/A')} ({first_pos.get('quantity', 0)})")
            print(f"      Response size: {len(json.dumps(positions_response))} bytes")
    except Exception as e:
        print(f"   ✗ Failed to fetch positions: {e}")
        return False
    print()

    # Step 6: Test fetching orders
    print("6️⃣  Testing orderbook() API call:")
    try:
        orders_response = client.orderbook()
        print(f"   ✓ orderbook() call successful")
        if isinstance(orders_response, dict):
            if "status" in orders_response:
                print(f"      Status: {orders_response.get('status')}")
            if "data" in orders_response:
                orders_data = orders_response.get("data", {})
                if isinstance(orders_data, dict):
                    orders = orders_data.get("orders", [])
                else:
                    orders = orders_data if isinstance(orders_data, list) else []
                print(f"      Orders found: {len(orders)}")
            print(f"      Response size: {len(json.dumps(orders_response))} bytes")
    except Exception as e:
        print(f"   ✗ Failed to fetch orders: {e}")
        return False
    print()

    print("=" * 70)
    print("✅ All tests PASSED! Streamlit can connect to OpenAlgo API")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  • API Key: Valid")
    print(f"  • Host: {host}")
    print(f"  • Funds: ✓ Accessible")
    print(f"  • Positions: ✓ Accessible ({len(positions)} found)")
    print(f"  • Orders: ✓ Accessible ({len(orders)} found)")
    print()
    print("Note: The Streamlit dashboard in the container should work fine!")
    return True

if __name__ == "__main__":
    success = test_streamlit_openalgo_connection()
    sys.exit(0 if success else 1)
