# HD Option Strategy - Automated Trading System

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-production-green.svg)]()

An automated trading system for **Nifty weekly options** that uses technical indicators (RSI Divergence + EMA filters) to generate buy signals and manages positions with real-time WebSocket monitoring and dynamic trailing stop loss.

---

## Features

| Feature | Description |
|---------|-------------|
| **Signal Generation** | RSI Divergence detection combined with EMA trend filters on 3-minute candles |
| **Entry Logic** | Four-gate system: Divergence -> Trend confirmation -> Trigger candle -> Risk check |
| **Position Management** | Real-time tick-by-tick monitoring via WebSocket once orders are placed |
| **Trailing Stop Loss** | Multi-stage exit with step-trailing (TSL) - moves SL in 0.5 RR increments |
| **Risk Controls** | Daily hard-SL cap (3 hits), signal cutoff at 15:00 IST, mandatory square-off at 15:15 IST |
| **Broker Integration** | OpenAlgo REST/WS client for live quotes and order placement |
| **Dry Run Mode** | Paper trading simulation without real capital deployment |

# HD Option Strategy - Automated Trading System

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-production-green.svg)]()

An automated trading system for **Nifty weekly options** that uses technical indicators (RSI Divergence + EMA filters) to generate buy signals and manages positions with real-time WebSocket monitoring and dynamic trailing stop loss.

---

## Features

| Feature | Description |
|---------|-------------|
| **Signal Generation** | RSI Divergence detection combined with EMA trend filters on 3-minute candles |
| **Entry Logic** | Four-gate system: Divergence -> Trend confirmation -> Trigger candle -> Risk check |
| **Position Management** | Real-time tick-by-tick monitoring via WebSocket once orders are placed |
| **Trailing Stop Loss** | Multi-stage exit with step-trailing (TSL) - moves SL in 0.5 RR increments |
| **Risk Controls** | Daily hard-SL cap (3 hits), signal cutoff at 15:00 IST, mandatory square-off at 15:15 IST |
| **Broker Integration** | OpenAlgo REST/WS client for live quotes and order placement |
| **Dry Run Mode** | Paper trading simulation without real capital deployment |

---

## Architecture

```
+-------------------------------------------------+
|               HD Strategy Engine                 |
+------------------+-------------------------------+
|  Signal Layer    |   Execution & Monitoring      |
+------------------+-------------------------------+
| - RSI Divergence | - STOP_LIMIT orders          |
| - EMA Filters    | - WebSocket LTP monitoring    |
| - Trigger candle | - Daily SL cap               |
```

---

## Quick Start

### Prerequisites

- **Python** >= 3.10
- `.env` file (copy from `.env.example`)

### Installation

```bash
cd Trading_Setups
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your OpenAlgo credentials
```

See `.env.example` for all available environment variables.

---

## Running the Strategy

### Live Trading (Paper / Dry Run)

```bash
python3 hd_strategy.py --mode paper
```

### Smoke Test

---

## Strategy Logic

### 1. Instrument Selection (09:20 IST)

- Fetch Nifty Spot LTP at market open (09:20).
- Round to nearest **50-point step** to find the ATM Strike.
- Lock corresponding CE and PE symbols for the current weekly expiry.

### 2. Technical Indicators (3-Min Candles)

| Indicator | Period / Notes |
|-----------|----------------|
| EMA 13, 20, 50 | Exponential moving averages on option premium |
| RSI | 3-period, applied to Close price |
| VWAP | Daily reset at market open |

### 3. Signal Generation - Four-Gate Entry

A buy signal fires only when all four gates pass:

1. **Divergence Gate**: Two fractal lows (P1 -> P2, 3-20 candles apart) where Low_P2 > Low_P1 AND RSI_P2 < RSI_P1, both below 20.
2. **Trend Gate**: EMA13 > EMA20 OR EMA20 > EMA50 (bullish trend confirmation).
3. **Trigger Candle**: Current candle must be a Strong Green (body >= 85% of range) or a Hammer (lower wick >= 2x body).
4. **Risk Gate**: Entry - SL <= 20 points, where:
   - Entry = Trigger Candle High + 1.0
   - Initial SL = Lowest low of (P1, P2, Trigger) - 1.0

### 4. Execution & Position Sizing

- **Lots**: 2 lots if Close > VWAP; 1 lot if Close <= VWAP.
- **Order Type**: STOP_LIMIT - Trigger at High + 1.0, Limit at Entry + 0.5.
- **WebSocket Activation**: Upon successful order placement, subscribe to tick-by-tick WebSocket for real-time LTP tracking.

### 5. Trailing Stop Loss (TSL) - Multi-Stage Exit

| Phase | Condition | Action |
|-------|-----------|--------|
| Phase 1 | Price < 1.5x IR from entry | SL stays at Swing Low - 1.0 |
| Phase 2 | Price reaches Entry + (1.5 x IR) | Move SL to Entry (breakeven). If only 1 lot -> close position |
| Phase 3 | Every 0.5 RR thereafter | Step-trail: SL advances by 0.5 RR increments |

- At 2.0 RR: Partial exit - sell 1 lot at market if initial was 2 lots.
- Continue trailing remaining lots every 0.5 RR until hit.

### 6. State Machine

| State | Description |
|-------|-------------|
| SEARCHING | Scanning 3-min candles for divergence patterns |
| PENDING | Order placed, waiting for WebSocket LTP confirmation |
| ACTIVE | Position filled, TSL being tracked in real-time |
| COMPLETED / CANCELLED | Trade closed or expired |


Fetch recent history and print a quick summary:

```bash
python3 hd_strategy.py --mode smoke
```

### Historical Replay (Backtest)

```bash
python3 hd_strategy.py --mode backtest --start 2025-01-01 --end 2025-06-30
```

> **Note**: CSV-based backtests are deprecated. Use `smoke` or `paper` modes for validation.

### Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--mode` | Mode: paper, smoke, backtest | paper |
| `--symbol` | Spot symbol override (e.g., NIFTY) | NIFTY |
| `--exchange` | Exchange override | - |
| `--start` / `--end` | Date range for backtests | - |
| `--diagnose` | Enable diagnostic mode | false |

---

## Project Structure

```
Trading_Setups/
├── hd_strategy.py          # Main strategy engine (~2011 lines)
├── hd_strategy.md          # Functional Requirements Document (FRD V3.0)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules
└── README.md               # This file
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| pandas | Data manipulation & indicator calculations |
| streamlit | Web dashboard (if used) |
| fyers-apiv3 | Fyers broker adapter (optional) |
| requests | HTTP requests for data fetching |
| python-dotenv | Load environment variables from .env |
| psycopg2-binary | PostgreSQL connectivity (if applicable) |
| sqlalchemy | Database ORM layer (if applicable) |
| openalgo | Primary broker client for quotes & orders |

---

## Logging

Detailed logs are produced at every candle close, including:

- Indicator values (RSI, EMA, VWAP)
- Divergence state progression
- Trigger detection and risk calculations
- WebSocket price events for TSL milestones
- Order fill prices vs. requested (slippage tracking)

---

## Notes & Warnings

- **This is a trading system.** Past performance does not guarantee future results. Always test thoroughly before using with real capital.
- The CSV-based historical backtest has been removed; use the smoke or paper modes for validation.
- Ensure your .env file is properly configured - missing credentials will prevent live execution.

---

## License

MIT License - see repository metadata for details.
| `--verbose` | Enable verbose console output | false |
| `--log-level` | Logging verbosity (DEBUG, INFO, etc.) | INFO |


# HD Option Strategy - Automated Trading System

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-production-green.svg)]()

An automated trading system for **Nifty weekly options** that uses technical indicators (RSI Divergence + EMA filters) to generate buy signals and manages positions with real-time WebSocket monitoring and dynamic trailing stop loss.
