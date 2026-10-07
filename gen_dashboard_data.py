#!/usr/bin/env python3
"""Quick script to generate fresh dashboard data with mode."""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Import the provider
from core.dashboard_data import DashboardDataProvider

# Create provider
provider = DashboardDataProvider(
    api_key=os.getenv("OPENALGO_API_KEY", "demo"),
    host=os.getenv("OPENALGO_HOST", "http://127.0.0.1:5002"),
)

# Get data
data = provider.get_account_summary()

# Write to file
output_path = Path("logs/dashboard_data.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, "w") as f:
    json.dump(data, f, indent=2)

print(f"✅ Dashboard data generated: {output_path}")
print(f"📊 Mode: {data.get('mode', 'UNKNOWN')}")
print(f"⏰ Timestamp: {data.get('timestamp', 'UNKNOWN')}")
print(f"\n📄 Sample output:")
print(json.dumps({
    "timestamp": data.get("timestamp"),
    "mode": data.get("mode"),
    "account_keys": list(data.get("account", {}).keys())[:5]
}, indent=2))
