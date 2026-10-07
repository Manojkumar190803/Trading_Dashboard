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


def get_current_mode() -> str:
    """Get the current OpenAlgo mode from environment."""
    # Try .env file first
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    
    # Check OPENALGO_MODE env var
    mode = os.getenv("OPENALGO_MODE", "").lower().strip()
    if mode in ("live", "analyzer"):
        return mode
    
    # Check STRATEGY_MODE
    strategy_mode = os.getenv("STRATEGY_MODE", "").lower().strip()
    if strategy_mode == "live":
        return "live"
    elif strategy_mode in ("paper", "backtest", "smoke"):
        return "analyzer"
    
    # Default
    return "analyzer"


def set_mode(new_mode: str) -> bool:
    """Set the OpenAlgo mode in .env file."""
    if new_mode not in ("live", "analyzer"):
        print(f"❌ Invalid mode: {new_mode}. Must be 'live' or 'analyzer'")
        return False
    
    env_file = Path(__file__).parent / ".env"
    
    if not env_file.exists():
        # Create .env file
        print(f"📝 Creating .env file at {env_file}")
        env_file.write_text("")
    
    # Set the environment variable
    set_key(str(env_file), "OPENALGO_MODE", new_mode)
    print(f"✅ Set OPENALGO_MODE={new_mode} in {env_file}")
    
    # Also print what to do to apply changes
    print("\n📋 To apply changes:")
    print("   1. The React dashboard will detect the mode change within 1 second")
    print("   2. For running processes, restart with:")
    print("      - docker-compose restart react_dashboard  (React dashboard)")
    print("      - Restart strategy workers if they check env")
    
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
