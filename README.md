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

# 9:30 OPT-Buy tick backtest
python3 -m strategies.opt_buy_930 \
	--candidates data/opt_buy_candidates.csv \
	--ticks data/opt_buy_ticks.csv \
	--csv logs/opt_buy_930_trades.csv \
	--txt logs/opt_buy_930_trades.txt

# Live trading
python3 run_strategy.py --script SENSEX --strategy hd --mode live

# Smoke test (fetch data, print indicators)
python3 run_strategy.py --script NIFTY --strategy hd --mode smoke
```

The 9:30 OPT-Buy backtest uses a dedicated tick path because selection occurs
at 09:25 and entry confirmation occurs at 09:30. The candidate CSV must contain
`symbol,side,strike,premium` and may include `tradable`. The tick CSV must
contain `timestamp,side,price`, with ISO timestamps in IST. Defaults are a
10-second sustained premium above 180, 130 units, a 20-point stop loss, and a
40-point target. Use `--quantity` and `--sustain-seconds` for overrides.

### EMA21 Profit Booking and Trailing Stop

EMA21 uses the filled option entry price and initial stop loss to calculate
risk (`1R`). For a 2-lot position:

- At `1.5R`, the stop loss moves to the entry price (breakeven).
- At `2.0R`, one lot is booked with a market exit and the remaining lot stays open.
- After `2.0R`, the remaining lot's stop loss advances by `0.5R` for each additional
	`0.5R` milestone. The stop can only move in the profitable direction.

For a 1-lot position, no partial booking occurs: the lot remains open after
`1.5R` and is trailed until the active trailing SL is hit. Failed or unavailable
LTP responses do not trigger a false trailing-stop exit.

For a one-week OpenAlgo historical run using 1-minute closes as the available
historical approximation of ticks:

```bash
python3 -m scripts.run_opt_buy_930_openalgo_backtest \
	--start 2026-08-17 \
	--end 2026-08-21 \
	--csv logs/opt_buy_930_week.csv \
	--txt logs/opt_buy_930_week.txt
```

This requires a valid OpenAlgo/Fyers session in `.env`. The historical API
does not provide true tick replay in this repository, so the output must not
be treated as equivalent to a tick-accurate backtest.

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

# EMA21 policy
EMA21_TIMEFRAME_MINUTES=3
EMA21_MARKET_OPEN=09:20
EMA21_ATM_LOCK_TIME=09:20
EMA21_ENTRY_START=09:20
EMA21_SIGNAL_CUTOFF=14:45
EMA21_ENTRY_CUTOFF=14:45
EMA21_MARKET_CLOSE=15:10
EMA21_FORCE_SQUARE_OFF=15:10
EMA21_MAX_OPTION_RISK_POINTS=20.0
EMA21_MAX_TRADES_PER_DAY=3
```

---

## Tests

```bash
python3 -m pytest tests/ -v
```

---

## Docker

```bash
# Run intraday live for NIFTY and BANKNIFTY in parallel:
# - NIFTY (EMA21)
# - BANKNIFTY (EMA21)
docker compose up -d

# Follow logs for all live services
docker compose logs -f

# Follow logs for one script
docker compose logs -f live_nifty
docker compose logs -f live_banknifty

# Restart only one script service
docker compose restart live_nifty

# Run a single script service (if needed)
docker compose up -d live_nifty

# Stop
docker compose down
```

Each service runs the EMA21 strategy in IST timezone, auto-restarts on crash, and injects a script-specific `SCRIPT` value into `run_strategy.py --mode live --strategy ema21`. The Docker image includes only the shared runtime files and EMA21 strategy implementation.

---

## License

MIT

for backtesting verbose logging with CSV save
 .venv/bin/python run_strategy.py --strategy hd,cd,tc --mode backtest --start 2026-08-10 --end 2026-08-10 --verbose-csv logs/live_runs/verbose_2026-08-10.csv