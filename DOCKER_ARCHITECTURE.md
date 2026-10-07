# Docker Architecture & Data Flow

## Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Compose Network                       │
│                    (trading-network)                             │
└─────────────────────────────────────────────────────────────────┘
           │                │                │                │
           │                │                │                │
    ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐
    │   Strategy  │  │  Dashboard  │  │    React   │  │ Streamlit  │
    │   Worker    │  │  Exporter   │  │ Dashboard  │  │ Interface  │
    │             │  │             │  │            │  │            │
    │ Port: -     │  │ Port: -     │  │ Port: 3000 │  │ Port: 8502 │
    │ Python      │  │ Python      │  │ Node.js    │  │ Python     │
    │ run_        │  │ export_     │  │ Vite Dev   │  │ Streamlit  │
    │ strategy.py │  │ dashboard_  │  │ Server     │  │ app        │
    │             │  │ data.py     │  │            │  │            │
    └──────┬──────┘  └──────┬──────┘  └──────┬─────┘  └────────────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                  ┌─────────▼──────────┐
                  │ Shared Volumes:    │
                  │ ./logs:/app/logs   │
                  │ ./data:/app/data   │
                  └───────────────────┘
```

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    External Systems                              │
│  ┌──────────────┐              ┌──────────────┐                │
│  │  OpenAlgo    │              │    Fyers     │                │
│  │  Broker API  │              │  Wallet API  │                │
│  │ :5002        │              │ (optional)   │                │
│  └──────┬───────┘              └──────┬───────┘                │
│         │                             │                        │
│         └─────────────┬───────────────┘                        │
│                       │                                        │
│                       │ HTTP                                  │
└───────────────────────┼──────────────────────────────────────┘
                        │
                        │ (via host.docker.internal)
                        │
           ┌────────────▼──────────────┐
           │  Dashboard Exporter       │
           │  (dashboard_exporter)     │  Every 5 seconds:
           │                           │  - Fetch positions
           │  export_dashboard_        │  - Fetch orders
           │  data.py                  │  - Fetch account funds
           │                           │  - Fetch wallet (Fyers)
           └────────────┬──────────────┘
                        │
                        │ Write JSON files
                        │
                ┌───────▼────────┐
                │ Shared Volume  │
                │ ./logs/        │
                │ - dashboard_   │
                │   data.json    │
                │ - wallet_      │
                │   data.json    │
                └───────┬────────┘
                        │
            ┌───────────┼───────────┐
            │           │           │
            │           │           │
    ┌───────▼───┐  ┌────▼────┐  ┌──▼──────┐
    │ Strategy  │  │  React  │  │Streamlit│
    │ Worker    │  │Dashboard│  │Interface│
    │(reads     │  │ (serves │  │(reads  │
    │ for data) │  │ via API)│  │ data)   │
    │           │  │         │  │         │
    │ Port:     │  │Port:3000│  │Port:8502│
    │ localhost │  │http://  │  │http://  │
    │           │  │localhost│  │localhost│
    │ Executes: │  │:3000/   │  │:8502    │
    │ - Finds   │  │logs/    │  │         │
    │   signals │  │*.json   │  │         │
    │ - Places  │  │         │  │         │
    │   orders  │  │Displays:│  │Displays:│
    │ - Manages │  │- Metrics│  │- Charts │
    │   trades  │  │- Status │  │- Logs   │
    └───────────┘  │- Sync   │  │- Trades │
                   │  time   │  │         │
                   └─────────┘  └─────────┘
```

## Component Communication

```
Strategy Worker (EMA21SignalProvider)
├─ Monitors live feed (NIFTY options)
├─ Calculates EMA21 indicators
├─ Generates buy/sell signals
├─ Sends orders to OpenAlgo via API
└─ Logs trade history → ./logs/*.csv

Dashboard Exporter
├─ Polls OpenAlgo every 5 seconds
│  ├─ POST /api/v1/positionbook → positions
│  ├─ POST /api/v1/orderbook → orders
│  └─ POST /api/v1/funds → account balance
├─ Optionally polls Fyers wallet API
└─ Writes JSON to ./logs/dashboard_data.json
   └─ Format: {account: {...}, positions: [...], orders: [...]}

React Dashboard (Vite Dev Server)
├─ Listens on :3000
├─ HMR enabled for live code reload
├─ Fetches ./logs/dashboard_data.json every 10s
├─ Fetches ./logs/wallet_data.json (if available)
├─ Displays real-time metrics:
│  ├─ Net MTM (₹)
│  ├─ Available Margin (₹)
│  ├─ Active Trades (#)
│  └─ Engine Status
└─ Mode detection: live (Fyers) vs analyzer (OpenAlgo)

Streamlit Interface
├─ Listens on :8502
├─ Reads trade history from ./logs/
├─ Displays analytics:
│  ├─ Win rate
│  ├─ P&L charts
│  └─ Trade logs
└─ Static page refresh
```

## File Structure

```
openalgo_buying_setups/
├── docker-compose.yml           ← Defines all 4 services
├── docker-compose.override.yml  ← Dev overrides (volume mounts, hot reload)
├── Dockerfile                   ← Strategy & Dashboard Exporter image
├── Dockerfile.react             ← React Dashboard image  
├── Dockerfile.streamlit         ← Streamlit Interface image
├── Dockerfile.backtest          ← Backtest runner image
│
├── frontend-react/
│  ├── src/
│  │  ├── pages/Dashboard.tsx   ← Clean 4-card hero design
│  │  ├── hooks/useData.ts      ← Polling hooks for JSON files
│  │  └── utils/realData.ts     ← Data transformation functions
│  ├── public/logs/             ← Static JSON serving (dev)
│  └── vite.config.ts           ← Plugin: serveLogsPlugin()
│
├── core/
│  ├── broker.py                ← OpenAlgo API client
│  ├── dashboard_data.py        ← DashboardDataProvider class
│  └── runner.py                ← Strategy execution loop
│
├── strategies/
│  └── ema21.py                 ← EMA21SignalProvider
│
├── logs/                        ← Shared volume (read/write)
│  ├── dashboard_data.json      ← Current account state
│  ├── wallet_data.json         ← Fyers wallet (if configured)
│  ├── *.csv                    ← Trade history, signals
│  └── *.txt                    ← Monitoring logs
│
└── .env                         ← Configuration
   ├── OPENALGO_API_KEY
   ├── OPENALGO_HOST
   └── EMA21_* strategy params
```

## Environment Variables Flow

```
.env file
├─ OPENALGO_API_KEY
├─ OPENALGO_HOST
├─ EMA21_TIMEFRAME_MINUTES
├─ EMA21_MAX_TRADES_PER_DAY
└─ etc.
    │
    ├──► strategy_worker
    │    ├─ Uses OpenAlgo client
    │    └─ Configures strategy parameters
    │
    ├──► dashboard_exporter
    │    ├─ API_KEY for authentication
    │    ├─ STRATEGY_MODE (analyzer/live)
    │    └─ EXPORT_INTERVAL (5s)
    │
    ├──► react_dashboard
    │    └─ VITE_* env variables (build-time)
    │
    └──► streamlit_interface
         └─ PYTHONUNBUFFERED=1
```

## Networking

```
Container Network: trading-network

All containers can reach each other by service name:
- strategy_worker
- dashboard_exporter
- react_dashboard
- streamlit_interface

External access:
- React Dashboard:  http://localhost:3000
- Streamlit:        http://localhost:8502
- Strategy: logs only

Docker Desktop networking:
- host.docker.internal:5002  → OpenAlgo API
- host.docker.internal:8766  → OpenAlgo WebSocket
```

## Volume Mounts

```
Each container has:

strategy_worker:
├─ ./logs:/app/logs          (Read/Write - trades, signals)
└─ ./data:/app/data          (Read/Write - caches, state)

dashboard_exporter:
├─ ./logs:/app/logs          (Read/Write - JSON exports)
└─ ./data:/app/data          (Read/Write)

react_dashboard:
├─ ./frontend-react/src:/app/src        (Dev hot reload)
├─ ./frontend-react/public:/app/public  (Dev hot reload)
└─ ./logs:/app/logs                     (Read-only - serves JSON)

streamlit_interface:
├─ ./frontend:/app/frontend  (Streamlit app code)
├─ ./logs:/app/logs          (Read-only - analytics data)
└─ ./data:/app/data          (Read/Write)
```

---
**This diagram explains why containers weren't visible before:**
- Build failed on `COPY logs ./logs` → No containers could start
- After fix: All 4 containers build and run successfully
- Data flows from brokers → exporter → JSON files → dashboards
