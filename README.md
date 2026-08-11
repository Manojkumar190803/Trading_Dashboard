# OpenAlgo Buying Setups

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Automated trading system for **Nifty weekly options** using RSI divergence strategies on 3-minute candles. Supports multiple independent strategies running simultaneously with real-time WebSocket monitoring and step-trailing stop loss.

---

## Strategies

| Strategy | Signal Logic | Entry Gate |
|----------|-------------|------------|
| **HD** (Hidden Divergence) | Price HL + RSI LL (trend continuation) | EMA trend filter + 1 trigger candle |
| **CD** (Classic Divergence) | Price LL + RSI HL (reversal) | No trend filter + 2 consecutive confirmation candles |
| **TC** (Trend Continuation) | 2 bullish momentum candles + high-volume red pullback | EMA alignment + red candle structure/volume rules |

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
python3 run_strategy.py --script NIFTY --strategy hd --mode backtest --start 2026-08-01 --end 2026-08-07

# Paper trading (dry run, real data)
python3 run_strategy.py --script BANKNIFTY --strategy cd --mode paper

# TC strategy
python3 run_strategy.py --script NIFTY --strategy tc --mode paper

# Live trading
python3 run_strategy.py --script SENSEX --strategy hd --mode live

# Smoke test (fetch data, print indicators)
python3 run_strategy.py --script NIFTY --strategy hd --mode smoke
```

### Multi-Strategy (Independent Execution)

Both strategies run independently — each has its own positions, SL cap, and PnL.

```bash
# Backtest all (single data fetch, combined summary)
python3 run_strategy.py --strategy hd,cd,tc --mode backtest --start 2026-08-01 --end 2026-08-07

# Paper trade all simultaneously
python3 run_strategy.py --strategy hd,cd,tc --mode paper

# Live trade all simultaneously
python3 run_strategy.py --strategy hd,cd,tc --mode live
```

### CLI Options

| Argument | Description | Default |
|----------|-------------|---------|
| `--script` | Underlying script: `NIFTY`, `BANKNIFTY`, `SENSEX` (strike step, lot size, option root, exchanges, weekly expiry are discovered from OpenAlgo) | `NIFTY` |
| `--strategy` | Strategy name(s), comma-separated: `hd`, `cd`, `tc`, `hd,cd,tc` | `hd` |
| `--mode` | `backtest`, `smoke`, `paper`, `live` | `smoke` |
| `--start` | Backtest start date (YYYY-MM-DD) | — |
| `--end` | Backtest end date (YYYY-MM-DD) | today |
| `--symbol` | Manual override for spot/option root symbol after discovery | discovered from `--script` |
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
│   ├── cd.py              # Classic Divergence signal logic
│   └── tc.py              # Trend Continuation signal logic
├── docs/
│   ├── hd.md              # HD strategy FRD (V3.0)
│   ├── cd.md              # CD strategy FRD (V1.2)
│   └── tc.md              # TC strategy FRD (V1.1)
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
# Run intraday live for all scripts in parallel:
# - NIFTY (HD+CD)
# - BANKNIFTY (HD+CD)
# - SENSEX (HD+CD)
docker compose up -d

# Follow logs for all live services
docker compose logs -f

# Follow logs for one script
docker compose logs -f live_nifty
docker compose logs -f live_banknifty
docker compose logs -f live_sensex

# Restart only one script service
docker compose restart live_nifty

# Run a single script service (if needed)
docker compose up -d live_nifty

# Stop
docker compose down
```

Each service runs in IST timezone, auto-restarts on crash, and injects script-specific `SCRIPT` value into `run_strategy.py --mode live --strategy hd,cd,tc`.

---

## License

MIT

for backtesting verbose logging with CSV save
 .venv/bin/python run_strategy.py --strategy hd,cd,tc --mode backtest --start 2026-08-10 --end 2026-08-10 --verbose-csv logs/live_runs/verbose_2026-08-10.csv