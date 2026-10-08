#!/usr/bin/env python3
"""
Utility script to set and display OpenAlgo mode (live or analyzer).
Changes are reflected immediately in the React dashboard.

Usage:
    python3 set_openalgo_mode.py --set live      # Switch to live mode
    python3 set_openalgo_mode.py --set analyzer  # Switch to analyzer mode
    python3 set_openalgo_mode.py --get           # Display current mode
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv, set_key

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.dashboard_data import DashboardDataProvider


def get_current_mode() -> str:
    """Get the current OpenAlgo mode from dashboard provider."""
    try:
        provider = DashboardDataProvider(
            api_key=os.getenv("OPENALGO_API_KEY", "demo"),
            host=os.getenv("OPENALGO_HOST", "http://localhost:5010"),
        )
        return provider._detect_mode()
    except Exception:
        # Fallback to environment variables
        mode = os.getenv("OPENALGO_MODE", "").lower().strip()
        if mode in ("live", "analyzer"):
            return mode
        return "analyzer"


def set_mode(new_mode: str) -> bool:
    """Set the OpenAlgo mode using DashboardDataProvider."""
    if new_mode not in ("live", "analyzer"):
        print(f"❌ Invalid mode: {new_mode}. Must be 'live' or 'analyzer'")
        return False
    
    try:
        provider = DashboardDataProvider(
            api_key=os.getenv("OPENALGO_API_KEY", "demo"),
            host=os.getenv("OPENALGO_HOST", "http://localhost:5010"),
        )
        success = provider.set_mode(new_mode)
        
        if success:
            # Also set environment variable for backward compatibility
            env_file = Path(__file__).parent / ".env"
            if not env_file.exists():
                env_file.write_text("")
            set_key(str(env_file), "OPENALGO_MODE", new_mode)
            
            print(f"✅ Mode set to: {new_mode}")
            print(f"   File: logs/current_mode.txt")
            print(f"   Env:  OPENALGO_MODE (updated for compatibility)")
        else:
            print(f"❌ Failed to set mode")
            return False
    except Exception as e:
        print(f"❌ Error setting mode: {e}")
        return False
    
    # Print what to do to apply changes
    print("\n📋 Updates applied:")
    print("   ✓ The React dashboard will detect the mode change within 1 second")
    print("   ✓ Next export cycle will include the new mode")
    
    return True


def display_mode() -> None:
    """Display current mode and status."""
    current = get_current_mode()
    
    print("\n" + "=" * 60)
    print("OpenAlgo Mode Status".center(60))
    print("=" * 60)
    print(f"\n  Current Mode: {current.upper()}")
    
    if current == "live":
        print("  Status: 🔴 LIVE TRADING (Real orders & positions)")
        print("  Risk Level: HIGH - Real money at stake")
    else:
        print("  Status: 🔵 ANALYZER MODE (Paper trading / Analysis)")
        print("  Risk Level: LOW - Safe for testing")
    
    print("\n  Dashboard Location: http://localhost:3000")
    print("  Mode updates reflected every 1 second\n")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Manage OpenAlgo mode (live or analyzer)"
    )
    parser.add_argument(
        "--set",
        choices=["live", "analyzer"],
        help="Set OpenAlgo mode",
    )
    parser.add_argument(
        "--get",
        action="store_true",
        help="Display current mode",
    )
    
    args = parser.parse_args()
    
    if args.set:
        success = set_mode(args.set)
        sys.exit(0 if success else 1)
    elif args.get:
        display_mode()
        sys.exit(0)
    else:
        # Default: display current mode
        display_mode()
        sys.exit(0)


if __name__ == "__main__":
    main()
