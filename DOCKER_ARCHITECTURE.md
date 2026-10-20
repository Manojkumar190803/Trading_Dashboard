# Docker Architecture & Data Flow

## Container Architecture

The current Compose deployment has five services:

| Service | Responsibility | Host access |
|---------|----------------|-------------|
| `strategy_worker` | Flask API on port 5003; does not launch a hard-coded live strategy in Compose | `localhost:5003` |
| `hd_strategy_daemon` | Legacy service name; manages all strategies from active dashboard instruments | Internal only |
| `dashboard_exporter` | Reads broker account data and writes dashboard JSON snapshots | Internal only |
| `react_dashboard` | React/Vite dashboard; proxies API requests to `strategy_worker` | `localhost:3000` |
| `streamlit_interface` | Legacy Streamlit dashboard | `localhost:8502` |

Services communicate over the Compose network. The worker and strategy daemon
share `logs` and `data` volumes with the exporter. React's health check probes
`127.0.0.1:3000` from inside its container.

## Data Flow Diagram

> The illustration below is a historical layout. For current service
> responsibilities, use the container table above and the component flow
> below: `strategy_worker` serves the API; `hd_strategy_daemon` runs active
> dashboard-configured strategies.

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
Strategy daemon (`hd_strategy_daemon`; legacy service name)
├─ Polls the instrument API every five seconds
├─ Starts only ACTIVE instruments; excludes INACTIVE and ARCHIVED rows
└─ Stops a runner when its instrument is deactivated or removed

Strategy runner (one process per active instrument)
├─ Monitors the configured index/options feed
├─ Calculates indicators and generates strategy signals
├─ Sends orders to OpenAlgo via API
└─ Writes strategy logs to ./logs/

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
├── docker-compose.yml           ← Defines five Compose services
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
**Historical Docker build issue (2026-10-07):**
- Build failed on `COPY logs ./logs` → No containers could start
- Logs are mounted as runtime volumes instead of copied into the image
- Current service responsibilities are described at the top of this document
