#!/usr/bin/env python3
"""Test OpenAlgo API connection and authentication"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Get credentials from environment
api_key = os.getenv("OPENALGO_API_KEY", "").strip()
host = os.getenv("OPENALGO_HOST", "http://localhost:5002").strip()

print("=" * 60)
print("OPENALGO CONNECTION DIAGNOSTIC TEST")
print("=" * 60)
print()

# Display configuration
print("📋 Configuration:")
print(f"  HOST: {host}")
print(f"  API_KEY: {api_key[:20]}...{api_key[-20:] if len(api_key) > 40 else ''}")
print(f"  API_KEY_LENGTH: {len(api_key)} chars")
print()

# Step 1: Check environment variables
print("✓ Step 1: Environment Variables Check")
if not api_key:
    print("  ❌ OPENALGO_API_KEY is empty or not set!")
    sys.exit(1)
if not host:
    print("  ❌ OPENALGO_HOST is empty or not set!")
    sys.exit(1)
print("  ✓ Both credentials are set")
print()

# Step 2: Test direct HTTP request to OpenAlgo
print("✓ Step 2: Testing HTTP connectivity to OpenAlgo...")
try:
    import requests
    
    # Test positionbook endpoint
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    url = f"{host}/api/v1/positionbook"
    print(f"  URL: {url}")
    print(f"  Headers: Authorization: Bearer {api_key[:20]}...")
    
    response = requests.post(url, headers=headers, timeout=5)
    print(f"  Response Status: {response.status_code}")
    print(f"  Response Text: {response.text[:200] if response.text else '(empty)'}")
    
    if response.status_code == 403:
        print("  ❌ 403 FORBIDDEN - API key authentication failed!")
        print()
        print("  Debugging: Trying alternative header formats...")
        
        # Try without Bearer prefix
        alt_headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response2 = requests.post(url, headers=alt_headers, timeout=5)
        print(f"    With X-API-Key header: {response2.status_code}")
        
        # Try with api_key parameter
        response3 = requests.post(f"{url}?apikey={api_key}", timeout=5)
        print(f"    With query parameter: {response3.status_code}")
        
    elif response.status_code == 401:
        print("  ❌ 401 UNAUTHORIZED - Invalid API key!")
    elif response.status_code == 200:
        print("  ✓ 200 OK - Connection successful!")
        print(f"  Response: {response.json()}")
    elif response.status_code == 404:
        print("  ❌ 404 NOT FOUND - Invalid endpoint or host!")
    else:
        print(f"  ⚠ Unexpected status: {response.status_code}")
    
except requests.exceptions.ConnectionError as e:
    print(f"  ❌ Connection Error: {e}")
    print("     Cannot reach OpenAlgo at " + host)
except Exception as e:
    print(f"  ❌ Error: {e}")

print()

# Step 3: Test using openalgo library
print("✓ Step 3: Testing with openalgo Python library...")
try:
    from openalgo import api
    
    client = api(api_key=api_key, host=host)
    print("  ✓ OpenAlgo client initialized")
    
    # Test positionbook
    print("  Testing positionbook()...")
    result = client.positionbook()
    print(f"    Response: {json.dumps(result, indent=2)[:200]}...")
    
    if result and result.get("status") == "success":
        print("  ✓ Successfully fetched positions!")
    else:
        print(f"  ❌ Unexpected response: {result}")
    
except ImportError:
    print("  ⚠ openalgo package not installed")
except Exception as e:
    print(f"  ❌ Error: {e}")

print()
print("=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
