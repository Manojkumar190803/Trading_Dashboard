# OpenAlgo Buying Setups

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Automated trading system for **Nifty weekly options** using RSI divergence strategies on 3-minute candles. Supports multiple independent strategies running simultaneously with real-time WebSocket monitoring and step-trailing stop loss.

---

## Strategies

| Strategy | Signal Logic | Entry Gate |
|----------|-------------|------------|
| **HD** (Hidden Divergence) | Price HL + RSI LL (trend continuation) | EMA trend filter + 1 trigger candle |
| **CD** (Classic Divergence) | Price LL + RSI HL (reversal) | No trend filter + 2 consecutive confirmation candles |

Both strategies share the same engine infrastructure: ATM strike locking, VWAP position sizing, risk caps, and step-trailing SL.

---

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your OpenAlgo credentials
```

---

## Running

### Single Strategy

```bash
# Backtest
python3 run_strategy.py --strategy hd --mode backtest --start 2026-08-01 --end 2026-08-07

# Paper trading (dry run, real data)
python3 run_strategy.py --strategy cd --mode paper

# Live trading
python3 run_strategy.py --strategy hd --mode live

# Smoke test (fetch data, print indicators)
python3 run_strategy.py --strategy hd --mode smoke
```

### Multi-Strategy (Independent Execution)

Both strategies run independently — each has its own positions, SL cap, and PnL.

```bash
# Backtest both (single data fetch, combined summary)
python3 run_strategy.py --strategy hd,cd --mode backtest --start 2026-08-01 --end 2026-08-07

# Paper trade both simultaneously
python3 run_strategy.py --strategy hd,cd --mode paper

# Live trade both simultaneously
python3 run_strategy.py --strategy hd,cd --mode live
```

### CLI Options

| Argument | Description | Default |
|----------|-------------|---------|
| `--strategy` | Strategy name(s), comma-separated: `hd`, `cd`, `hd,cd` | `hd` |
| `--mode` | `backtest`, `smoke`, `paper`, `live` | `smoke` |
| `--start` | Backtest start date (YYYY-MM-DD) | — |
| `--end` | Backtest end date (YYYY-MM-DD) | today |
| `--symbol` | Override spot symbol | `NIFTY` |
| `--exchange` | Override spot exchange | `NSE_INDEX` |
| `--timeframe` | Override candle interval (minutes) | `3` |
| `--max-risk` | Override max option risk points | `20` |
| `--max-sl` | Override max SL hits per day | `3` |
| `--body-threshold` | Strong-green body % threshold | `0.85` |
| `--diagnose` | Print per-candle diagnostic when no signal | off |
| `--verbose` | Print full candle summary every bar | off |
| `--log-level` | Logging level (DEBUG, INFO, WARNING) | `INFO` |

---

## Project Structure

```
openalgo_buying_setups/
├── run_strategy.py         # Unified CLI entry point
├── core/
│   ├── engine.py           # Strategy-agnostic trade engine (entries, exits, TSL)
│   ├── runner.py           # Live feed + historical replay runners
│   ├── broker.py           # OpenAlgo broker interface
│   ├── indicators.py       # RSI, EMA, VWAP, candle pattern helpers
│   └── models.py           # Data models (Position, Signal, Config)
├── strategies/
│   ├── base.py             # SignalProvider ABC
│   ├── hd.py              # Hidden Divergence signal logic
│   └── cd.py              # Classic Divergence signal logic
├── docs/
│   ├── hd.md              # HD strategy FRD (V3.0)
│   └── cd.md              # CD strategy FRD (V1.2)
├── tests/
│   ├── test_cd_strategy.py
│   └── test_vwap_room_and_tsl.py
└── requirements.txt
```

---

## Environment Variables

```env
OPENALGO_API_KEY=your_api_key
OPENALGO_HOST=http://127.0.0.1:5002
OPENALGO_WS_URL=ws://127.0.0.1:8765
STRATEGY_NAME=Strategy
PRODUCT=MIS
```

---

## Tests

```bash
python3 -m pytest tests/ -v
```

---

## Docker

```bash
# Run both strategies live (uses .env for credentials)
docker compose up -d

# Override strategy or mode
STRATEGY=hd MODE=paper docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

The container runs in IST timezone, auto-restarts on crash, and uses `network_mode: host` to reach local OpenAlgo instances.

---

## License

MIT
