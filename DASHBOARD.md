# Trading Dashboard Guide

This guide covers the React dashboard pages, their data sources, and how
dashboard instrument settings reach the Python strategy processes. The
dashboard is for monitoring and configuration; it is not an order-entry
terminal.

For container setup and operations, see [DOCKER.md](DOCKER.md). Strategy
behavior is specified separately in [`docs/`](docs/).

## Application and Data Flow

The React/Vite frontend is served on port `3000`. It calls the Flask API
(port `5003`) for database-backed instrument and analytics data. Express
(port `4000`) serves selected files, reset operations, and the dashboard
snapshot stream. PostgreSQL stores instrument configuration; OpenAlgo provides
broker account and market data.

```text
OpenAlgo -> dashboard_exporter -> logs/dashboard_data.json
                                      |                  |
                                      v                  v
                               Express SSE         Positions /
                               -> Dashboard         Orderbook

React Instruments -> Flask API -> PostgreSQL -> strategy_daemon
                                               -> strategy runners
```

The browser never receives the OpenAlgo API key or connects directly to the
broker websocket. The dashboard snapshot stream is independent of the Python
strategy runner's market-data and order-execution connection.

## Pages

### Home (`/` or `/dashboard`)

Shows account summary information such as Net MTM, Available Margin, active
trades, broker identity, and strategy/status cards. The page receives account
snapshots over Express `/dashboard-stream` (SSE) and has a 120-second local
snapshot fetch as a fallback.

The exporter fetches a full account snapshot every 120 seconds while flat,
every 30 seconds with an open position, and after order-fill events. It also
applies active-position LTP websocket ticks to the snapshot. The frontend's
`Ready`/`Active` labels are not a health check of the strategy daemon; use the
instrument status and daemon logs to verify that a strategy process is running.

The page's **Test Activity** section is separate from the broker account
snapshot. It shows virtual open positions, P&L, completed trades, and Test
signals/events from `/api/test-trading`.

### Positions (`/positions`)

Reads positions from `logs/dashboard_data.json`, showing symbols, quantities,
entry/current prices, P&L, and related summary cards. It supports CSV export.
The page rereads the local snapshot every 60 seconds; its ticking clock is not
a broker refresh. It does not submit or close orders.

Live broker positions and Test virtual positions are displayed in separate
sections. Test positions and P&L come from the virtual trading ledger, not the
OpenAlgo account snapshot.

The displayed counts are based on rows in the current snapshot, not a durable
trade-history query. The open-position count currently includes only positive
quantities.

### Orderbook (`/orderbook`)

Displays broker/account orders from the account snapshot, including order
counts, statuses, and CSV export. It rereads the local snapshot every 60
seconds. It is read-only: it does not submit, modify, or cancel broker orders,
and it may show orders for instruments that are not currently active in the
Instruments page. Test virtual orders are shown separately and are not broker
orders.

### Analytics (`/analytics`)

Shows P&L and trade metrics, an equity curve, win/loss distribution, daily
performance charts, a daily P&L calendar, and monthly summary metrics. The
charts can change display style; the calendar supports month selection and
CSV export. **Test Performance** contains only virtual trading summaries and
completed Test trades. The remaining metrics, equity curve, trade distribution,
daily performance, calendar, and monthly summary are grouped under **Live
Performance** and use Live analytics data; Test results are not mixed into them.

| API | Purpose |
| --- | --- |
| `GET /api/analytics/summary` | Summary metrics synthesized from the current account snapshot. |
| `GET /api/analytics/daily?year=YYYY&month=MM` | Daily P&L and monthly summary for the requested period. |
| `POST /api/analytics/daily/reset?year=YYYY&month=MM` | Reset saved daily P&L for the selected period. |
| `GET /api/test-trading` | Aggregated per-instrument Test virtual positions, orders, trades, alerts, and P&L. |

Daily data can combine `logs/daily_pnl.json`, database records, and current
account snapshots. The calendar's trade count is based on completed BUY
entries; older records may not have a reliable count. Some trade rows can
fall back to `logs/analytics_trades.csv`, so not every chart or headline is a
single historical ledger.

Resetting analytics clears saved analytics data for its selected scope. It
does not cancel orders or close positions.

### Instruments (`/instruments`)

This page creates, edits, activates/deactivates, and archives strategy
instruments. It provides symbol search/validation, strategy selection, and
configuration for monitoring times, lot adjustment, maximum initial risk,
partial booking, daily losing-trade limits, and a per-instrument `LIVE` or
`TEST` execution mode. Existing and new instruments default to `LIVE`.

Instrument records are saved through Flask and stored in PostgreSQL. The
strategy daemon polls the API and starts runners for `ACTIVE` instruments.
The normal endpoints are `GET`/`POST /api/instruments` and
`PUT`/`DELETE /api/instruments/<id>`; `DELETE` archives the record rather than
hard-deleting it.

Dashboard values for 21EMA are passed to that instrument's runner as
process-specific environment overrides. They take precedence over `.env`
defaults without rewriting `.env`. The broker symbol selects the underlying;
`lotSizeAdjustment` is the number of option lots, and order quantity is that
number multiplied by the broker-discovered lot size. Monitoring start/end,
entry cutoff, maximum initial risk, partial-booking values, and daily losing
trade limit are also applied. A dashboard monitoring end may bring the
strategy's default 15:10 square-off earlier, but cannot delay it.

The daemon detects changes to active instrument settings and restarts the
corresponding runner. Deactivation stops future strategy management on the
next reconciliation; it does **not** cancel broker orders or close positions.
Check the broker separately.

In `TEST` mode, the runner uses live market data for strategy evaluation but
routes orders to its virtual Test broker. Test orders, positions, P&L, and
alerts are persisted separately in `logs/test_trading_<id>.json`; Test mode
does not submit order mutations to OpenAlgo or write into the shared Live
monitoring and alert records. Changing an instrument's mode does not change the
global OpenAlgo account mode.

### Logs (`/logs`)

Shows system/strategy logs, ATM lock information when available, triggered
alerts, and **Active Logs** for three-minute setup/candle activity. Active Logs
are grouped by strategy and CE/PE side, with current and previous setup details
and candle history. `Export 3-Min Logs` downloads the displayed setup/candle
events.

Triggered alerts can be exported. `Clear Messages` clears the current browser
messages/toasts. `Reset` hides existing alert rows using a reset marker; it
does not delete the CSV audit history. Dated files under `logs/` are polled
approximately every two seconds, so an empty page can mean no file has been
created for that date. Test signals and events are displayed in a separate
section sourced from `/api/test-trading`; they are not read from the Live alert
CSV files.

## Shared UI and Account Mode

The shared sidebar provides navigation, a collapsible layout, a browser-local
clock, and a dark/light theme toggle. Theme and other selected UI preferences
are stored in browser local storage; they are not shared across browsers and
are not the durable instrument database.

The dashboard's per-instrument `LIVE`/`TEST` selector is separate from the
global OpenAlgo `LIVE`/`ANALYZER` account mode. It does not switch the broker's
account mode. A `mode` field may be present in the account snapshot, but
changing it does not start, stop, or change a strategy runner. Use
`python3 set_openalgo_mode.py --get` to inspect the configured mode or
`python3 set_openalgo_mode.py --set analyzer` to change it. Recreate
`dashboard_exporter` for changed container environment values to take effect.
Verify broker and strategy mode before live trading.

## Data Sources and Refresh

| Data | Source | Used by |
| --- | --- | --- |
| Account, funds, positions, and orders | `dashboard_exporter` writes `logs/dashboard_data.json` from OpenAlgo | Home, Positions, Orderbook, some Analytics endpoints |
| Account snapshot stream | Express watches the JSON file and sends `/dashboard-stream` events | Home page |
| Instrument configuration/status | Flask API backed by PostgreSQL | Instruments page and strategy daemon |
| Strategy monitoring | `logs/monitoring_YYYYMMDD.csv` | Logs page |
| Strategy alerts | `logs/trade_alerts_<symbol>_YYYYMMDD.csv` | Logs page |
| Test virtual trading activity | `logs/test_trading_<id>.json`, aggregated by `/api/test-trading` | Dashboard, Positions, Orderbook, Analytics, and Logs Test sections |
| ATM lock | `logs/atm_lock_<symbol>_YYYYMMDD.json` | Logs page |
| Daily P&L history | `logs/daily_pnl.json` and PostgreSQL | Analytics page |
| Analytics fallback/reset state | `logs/analytics_trades.csv` and `logs/analytics_reset.txt` | Analytics page |

The Dashboard page listens to SSE with a 120-second snapshot fallback.
Positions and Orderbook reread the local snapshot every 60 seconds. Analytics
and Logs use their own API/file refresh intervals. These UI refreshes do not
guarantee that the underlying broker data is fresh.

## Run the Frontend Locally

The full application also needs Flask, PostgreSQL, OpenAlgo, and (for managed
live strategies) the Python daemon. Running the frontend alone is useful for
UI work but does not start those services.

```sh
cd frontend-react
npm install
npm run dev
```

Useful frontend checks, run from `frontend-react/`:

```sh
npm run type-check
npm run lint
npm run build
```

## Ports and Troubleshooting

| Port | Service |
| --- | --- |
| `3000` | React/Vite frontend |
| `4000` | Express helper and SSE stream |
| `5003` | Flask API |
| `5432` | PostgreSQL, external to the current Compose stack |

- If API-backed pages fail, check Flask logs, its PostgreSQL connection, and
  the frontend `API_TARGET`.
- If account data is stale, check `logs/dashboard_data.json`, exporter logs,
  OpenAlgo authentication, and that REST and websocket URLs reach the same
  OpenAlgo instance.
- If an instrument does not start, confirm its database status is `ACTIVE`
  and inspect `strategy_daemon` and per-instrument strategy logs.
- If Logs is empty, check whether the expected dated files exist under
  `logs/`.
- An inactive instrument may still appear in Orderbook or historical Logs;
  those pages are not proof that its runner is active.

## Source Files

| File | Responsibility |
| --- | --- |
| `frontend-react/src/pages/` | Dashboard, Positions, Orderbook, Analytics, Instruments, and Logs pages |
| `frontend-react/src/components/Layout.tsx` | Navigation, theme control, and shared layout |
| `frontend-react/src/hooks/useInstruments.ts` | Instrument API requests and mapping |
| `frontend-react/src/hooks/useData.ts` | Snapshot and analytics data access |
| `frontend-react/server.js` | Express file helpers, resets, and SSE |
| `api_server.py` | Flask API |
| `core/db_models.py` | Database models |
| `export_dashboard_data.py` | OpenAlgo account snapshot exporter |
| `strategy_daemon.py` | Active instrument reconciliation |
| `run_strategy.py` | Strategy runner entry point |
| `docker-compose.yml` | Service and runtime configuration |
