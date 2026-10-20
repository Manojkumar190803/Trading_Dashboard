# React Trading Dashboard Guide

This guide explains what the React dashboard is, how its parts fit together, how instrument settings reach the strategy processes, and how to run and troubleshoot it. It is written for someone who is new to this repository.

The dashboard is an operational interface, not a broker or exchange. Orders are sent by the Python strategy runtime through the configured OpenAlgo connection. Review the active instrument configuration and broker mode before starting live trading.

## 1. What This Project Does

The repository contains Python trading strategies and their runtime, a Flask API, a PostgreSQL database, and more than one user interface. The React dashboard is the browser interface for viewing account data, positions, orders, analytics, logs, and configured instruments.

The React app itself does not run trading strategies. It edits instrument configuration through the API and displays information produced by the strategy runtime or written to data files. A separate Python daemon decides which configured strategies should be running.

## 2. Terms You Will See

| Term | Meaning in this project |
| --- | --- |
| React frontend | The website displayed in the browser. It contains the dashboard pages and their user interactions. |
| Vite | The frontend development server and build tool. It serves the app on port `3000` and forwards API requests in development. |
| API | A web service that accepts requests from the frontend and reads or changes backend data. |
| Flask | The Python API service. It owns the current instrument CRUD endpoints and connects to PostgreSQL. |
| PostgreSQL | The database used to persist instrument configuration. |
| Strategy daemon | A Python process that periodically checks configured instruments and starts or stops strategy runner processes. |
| Strategy runner | A Python process executing a selected instrument/strategy combination. |
| OpenAlgo | The configured broker gateway used by the Python trading runtime to obtain broker data and submit orders. |
| Express | A small Node.js server used for file and legacy dashboard operations. It is not the current source of truth for instrument configuration. |
| Logs directory | The repository's `logs/` folder. It contains snapshots, monitoring files, analytics CSVs, and other runtime output. |
| MTM | Mark-to-market: the current estimated profit/loss on open holdings or positions. The displayed number depends on the account snapshot fields available. |
| ATM | At-the-money option strike. The runtime may lock a CE and PE contract for an instrument and session. |
| CE / PE | Call option / put option. The Logs page separates setup information for these two option sides. |
| RR | Risk-reward ratio, used by the trailing-stop settings panel. A value such as `1.25 RR` represents a profit milestone relative to the defined initial risk. |

## 3. Architecture

```text
Browser
  |
  +-- React 18 + TypeScript app (Vite, port 3000)
        |
        +-- /api/* ----------------------> Flask API (port 5003)
        |                                  |
        |                                  +--> PostgreSQL instrument records
        |
        +-- /logs/* ---------------------> runtime files in logs/
        |
        +-- some legacy/file operations -> Express server (port 4000)

   dashboard_exporter (Python) --> logs/dashboard_data.json + logs/wallet_data.json
                   |
                   +--> read by the React pages

PostgreSQL instrument records
  ^
  |
Python strategy daemon -- polls active instruments via the Flask API
  |
  +--> starts/stops Python strategy runners --> OpenAlgo --> broker
```

### Component responsibilities

| Component | Main responsibility |
| --- | --- |
| React/Vite | Renders the browser UI. Vite proxies `/api` to Flask and, in development, provides access to files in the repository's `logs/` directory. |
| Flask API (`api_server.py`) | Provides instrument CRUD, symbol search/validation, account/log data endpoints, and analytics endpoints. Instrument records are stored in PostgreSQL. |
| PostgreSQL | Durable store for instrument records, including their strategy, schedule, sizing, risk, and active/inactive status. |
| Python strategy daemon (`strategy_daemon.py`) | Reconciles running strategy processes against the configured active instruments. It does not rely on the browser being open. |
| Python strategy runner (`run_strategy.py`) | Executes the selected strategy for an instrument and communicates with the configured OpenAlgo service. |
| Dashboard exporter (`export_dashboard_data.py`) | Polls OpenAlgo and, when configured, Fyers; writes account and wallet snapshots into the shared `logs/` directory. Compose runs it in `both` mode every second. |
| Express (`frontend-react/server.js`) | Serves selected files and implements analytics/alert reset operations plus older instrument export/status routes. Treat those instrument routes as legacy; they are not the database-backed instrument CRUD API. |
| `logs/` files | Provide dashboard snapshots and file-based history/monitoring data. These files are not the source of truth for instrument activation. |

The React package is in [`frontend-react/package.json`](frontend-react/package.json). The frontend and backend use different languages and tools:

| Technology | Where it is used | Why it is here |
| --- | --- | --- |
| React 18 | Browser UI | Builds the dashboard from reusable pages and components. |
| TypeScript 5 | React source | Adds type checking to JavaScript application code. |
| React Router 6 | Frontend | Maps browser paths such as `/positions` to page components without a full page reload. |
| Vite 5 | Frontend development/build | Starts the development server, proxies API requests, serves development log files, and creates the frontend build. |
| Tailwind CSS 3, PostCSS, Autoprefixer | Frontend styling | Provides utility-based styling and CSS processing. The app also has custom global and theme CSS. |
| Zustand 4 | Frontend state | Shares UI state and persists a limited subset of preferences in browser local storage. It is not the instrument database. |
| Recharts 2 | Analytics | Draws the P&L charts and trade-distribution chart. |
| Lucide React | Frontend controls | Supplies icons used by navigation, buttons, and status indicators. |
| PapaParse 5 | CSV handling | Parses monitoring/alert CSVs in the browser. |
| clsx 2 | Frontend styling | Builds conditional CSS class lists. |
| Node.js, Express 4 | Frontend helper server | Express serves selected files and implements file-based and legacy operations. Vite and Express run concurrently in `npm run dev`. |
| Python, Flask | API and strategy runtime | Flask exposes backend routes; Python also runs strategy processes and their manager. |
| SQLAlchemy 2, PostgreSQL, psycopg | Backend persistence | SQLAlchemy maps Python objects to database records; PostgreSQL stores durable configuration and related records; psycopg connects Python to PostgreSQL. |
| Docker Compose | Local multi-service runtime | Starts the React service, API/worker, daemon, data exporter, and legacy Streamlit service together. |

The exact JavaScript dependency ranges are listed in `frontend-react/package.json`; the root `requirements.txt` lists Python dependencies. The root Compose setup also includes a Streamlit interface on port `8502`; it is a separate legacy UI, not a page inside the React app.

## 4. What You Can Do in the Dashboard

The routes are registered in [`frontend-react/src/App.tsx`](frontend-react/src/App.tsx). The sidebar links to:

| Page | Route | What it displays |
| --- | --- | --- |
| Dashboard | `/` or `/dashboard` | Account summary and broker snapshot information. |
| Positions | `/positions` | Positions from the account snapshot file. |
| Orderbook | `/orderbook` | Orders from the account snapshot file. These are broker/account orders, not only orders for currently active dashboard instruments. |
| Analytics | `/analytics` | Trade and P&L summaries from the API and analytics data sources. |
| Instruments | `/instruments` | Database-backed instrument configurations. This is where an instrument is added, edited, activated, or deactivated. |
| Logs | `/logs` | Strategy monitoring files, alert data, and other log information. |

### Shared application shell

Every page uses a collapsible left navigation sidebar. The sidebar also has a dark/light theme toggle; the theme is kept in browser local storage. The page header shows a clock formatted in the browser, not a timestamp returned by the broker or backend. Toast messages are used for some new log/alert events and operation results.

### Dashboard (`/` or `/dashboard`)

The home page is a quick account overview. It displays four cards: Net MTM, Available Margin, Active Trades, and Strategy. Net MTM and margin are derived from available account/wallet snapshot fields; active trades are estimated from non-zero account positions when account data is used. The account snapshot request is polled about once per second during market hours. The wallet snapshot is polled about once per second without the same market-hours gate. Both are files generated by the dashboard exporter, not direct browser-to-broker requests.

**Important:** the current page sets its engine label to `Ready` and its strategy card to `Active` in frontend state. These labels are not a live health check of the Python daemon or proof that a runner is executing. Its “last updated” clock is generated by the browser. Use daemon/container logs and configured instrument status to verify the real runtime.

The frontend selects its displayed account mode based on whether wallet data exists. The Compose exporter runs in `both` mode and can create wallet data from OpenAlgo as a fallback when Fyers credentials are unavailable. Consequently, the page's displayed `live` mode is not sufficient evidence that wallet values came from Fyers; inspect the exporter configuration and snapshot if that distinction matters.

### Positions (`/positions`)

This page reads positions from the account snapshot and presents four summary cards, a position table, and a live-price card for positions with positive quantity. The table includes symbol, average entry price, last/current price, quantity, P&L, P&L percent, and a profit/loss badge. `Export CSV` downloads the displayed position rows. The page polls the account snapshot about once per second during market hours.

The page's counts and “today” labels are derived from the positions currently present in the snapshot; they are not a separate, durable trade-history query. Its open-position count currently counts positions whose quantity is greater than zero, so do not rely on that count for short/negative-quantity positions. It does not place or close orders.

### Orderbook (`/orderbook`)

The page polls account snapshot data about every five seconds and shows counts for buy, sell, completed, open, and rejected orders. It has two sections: an execution log for completed/cancelled entries and a list of orders from the broker snapshot, including status, quantity/filled quantity, price, trigger price, and timestamp. Each section has a CSV export.

This is a monitoring/export view. It does not provide controls to submit, modify, or cancel broker orders. The list can contain orders for symbols that are not currently active in the Instruments page.

### Analytics (`/analytics`)

Analytics displays net profit/loss, win rate, profit factor, and completed-trade metrics; an equity curve; winning-versus-losing trade distribution; daily gain/loss chart; profitability/risk summary; daily P&L calendar; and monthly summary. The equity chart can switch between area, bar, and line styles. The daily chart can switch between bar and line. The calendar lets the user select month/year, export daily P&L CSV, and reset that month's saved daily P&L. The page also has an overall analytics CSV export and an analytics reset action.

The page obtains its headline summary from Flask, which calculates it from the current `dashboard_data.json` snapshot: positions contribute the current P&L and wins/losses, while completed orders contribute the completed-order count. When constructing a trade list, the frontend can convert those orders into rows with zero P&L; it falls back to `logs/analytics_trades.csv` if the API path is unavailable. The daily calendar is a different source: Flask combines the daily P&L archive, database snapshots, and the current-day account snapshot where available. Do not assume every chart and headline is a single historical ledger or that all totals have the same time window. Resetting analytics changes saved analytics/reset data; use it only when intended. It is not a broker order or position action.

### Instruments (`/instruments`)

This is the configuration and activation page for strategy-managed instruments. It provides name search, strategy filtering, an add/edit form, active/inactive groupings, status toggle, edit, and archive/delete actions. The form supports:

- Instrument name and broker symbol. Symbol suggestions are searched from the backend; the selected symbol is validated through an API request.
- Strategy selection: `21EMA`, `HD`, `CD`, `TC`, `2BC`, or `BO`.
- Monitoring start and end times; HD additionally exposes an entry cutoff and maximum initial-risk value.
- Lot-size adjustment and a read-only calculated lot size. The current frontend mapping is NIFTY/NIFTY50 `65`, BANKNIFTY `30`, SENSEX `20`, and `1` for an unrecognized name, multiplied by the adjustment. Confirm the correct lot size for the current contract before activation.
- Product type, currently fixed as `INTRADAY` in the form.

The page has a separate global trailing-stop panel for breakeven RR, trailing-step RR, and a global maximum initial risk default. Its visible controls and the current file-export integration are described under [Settings and runtime configuration](#settings-and-runtime-configuration).

The UI's delete confirmation says “permanently delete,” but the Flask `DELETE` endpoint actually sets the record to `ARCHIVED`; it does not hard-delete the database row. Archived records are not shown in the normal active/inactive list. Creating a configuration with the same name restores the existing archived record and activates it.

### Logs (`/logs`)

The Logs page is the strategy activity monitor. It shows active instrument/setup context, ATM lock state where lock files exist, strategy setup status by call (`CE`) and put (`PE`) side, and recent completed three-minute candle/setup history including OHLC values when available. Its “Export 3-Min Logs” action exports the displayed setup/candle log data.

The Triggered Alerts table shows time, strategy, symbol, event type, and message. It refreshes from dated per-symbol alert CSV files. New alerts may also produce toast messages. `Export` downloads visible alerts. `Clear Messages` clears the current browser view/toasts, whereas `Reset` writes a reset marker so existing alerts are hidden from the view without deleting the CSV audit history; later alerts can still appear. Level and strategy filters are available for the general log list, and INFO-level rows are excluded from that filtered list.

The page polls monitoring/alert data and ATM lock files about every two seconds. It depends on current-date files under `logs/`, so an empty page can mean no file has been generated, not necessarily that the React app is broken.

### Data files, APIs, and refresh behavior

The React app reads from multiple backend interfaces. There is no single database table containing every value displayed on every page.

| Data | Producer/source | Used for |
| --- | --- | --- |
| `logs/dashboard_data.json` | `export_dashboard_data.py`, through the `dashboard_exporter` Compose service | Account summary, positions, orders, and Flask's current analytics summary. |
| `logs/wallet_data.json` | The same exporter; Fyers when credentials are available, otherwise OpenAlgo fallback in Compose `both` mode | Dashboard balance/MTM card values. |
| `logs/monitoring_YYYYMMDD.csv` | Strategy runtime | Setup status and three-minute candle history in Logs. |
| `logs/trade_alerts_<symbol>_YYYYMMDD.csv` | Strategy runtime | Triggered alerts shown by Logs. |
| `logs/atm_lock_<symbol>_YYYYMMDD.json` (HD may include `_HD`) | Strategy runtime | Locked CE/PE contract display in Logs. |
| `logs/analytics_trades.csv` and `logs/analytics_reset.txt` | Analytics/export processes and Express reset route | Analytics trade fallback and overall analytics reset state. |
| `logs/daily_pnl.json` and PostgreSQL daily P&L records | Flask analytics endpoints | Historical daily calendar and monthly totals. |
| PostgreSQL instrument records | Flask API | Instrument settings and status used by the daemon. |

Primary Flask routes include `GET /api/health`, the instrument and symbol routes listed above, `GET /api/analytics/summary`, `GET /api/analytics/daily?year=YYYY&month=MM`, `POST /api/analytics/daily/reset?year=YYYY&month=MM`, and database reporting routes under `/api/db/`. Express separately implements `GET /health`, `GET /logs/<filename>`, overall analytics reset, alert reset/status, and legacy instrument export/status routes. In Vite development, `/api/*` is proxied to Flask; Vite also serves `.json`, `.txt`, and `.csv` files from the repository's `logs/` directory. Some Logs UI calls explicitly use Express on port `4000`.

Typical polling intervals are about one second for account data during market hours, one second for wallet data, five seconds for Orderbook, three seconds for Analytics summary/trades, and two seconds for Logs monitoring/alerts/ATM files. Polling is not a guarantee that the producer or broker has generated fresh data at that frequency.

### What the dashboard does not do

The React dashboard is not an order-entry terminal. It does not itself evaluate strategy rules or submit/cancel broker orders. Its main operational control is instrument configuration and activation; the Python daemon and runners do the strategy work. The visible account/order/position pages display snapshots and are not substitutes for confirming current broker state.

## 5. Instrument Configuration and Strategy Startup

The Instruments page uses [`frontend-react/src/hooks/useInstruments.ts`](frontend-react/src/hooks/useInstruments.ts) to call the Flask API. The main endpoints are:

| Method and path | Purpose |
| --- | --- |
| `GET /api/instruments` | List active instruments. |
| `GET /api/instruments/debug/all` | List all records, including inactive or archived records; used by the management UI when it needs those records. |
| `POST /api/instruments` | Create an instrument. |
| `PUT /api/instruments/<id>` | Update configuration or status. |
| `DELETE /api/instruments/<id>` | Archive an instrument by setting its status to `ARCHIVED`; this is not a hard delete. Prefer deactivation (`INACTIVE`) when the goal is to stop future execution while keeping the configuration active in the management list. |
| `GET /api/symbols/search` | Search available broker symbols. |
| `POST /api/symbols/validate` | Validate a symbol through the backend integration. |

The normal lifecycle is:

1. An operator creates or edits an instrument in the React Instruments page.
2. React sends the change to Flask; Flask persists it in PostgreSQL.
3. The strategy daemon polls the backend and selects records with `ACTIVE` status.
4. The daemon starts or maintains a runner for each active instrument/strategy configuration, and stops runners that are no longer managed as active.
5. A runner obtains market/account information and submits strategy orders through the configured OpenAlgo connection.

Creating an instrument with a name that already exists but is archived restores that existing record and activates it; the name is not duplicated.

In Docker, the `strategy_worker` service runs the API only; the daemon is responsible for managed live strategy execution. This prevents a separately configured worker process from independently launching a strategy outside the active-instrument configuration.

### Deactivation is not order cancellation

Changing an instrument to inactive prevents the daemon from continuing to manage its strategy after the next reconciliation. It does **not** cancel orders already accepted by the broker, close an open position, or reverse a fill. Check the broker and manage existing orders/positions separately.

The Logs page and broker Orderbook can show historical or still-open activity for an instrument that is now inactive. Seeing an instrument in those pages does not, by itself, mean its strategy is currently running.

### Source-of-truth distinction

The active database records and the daemon's API-based selection control the current Docker strategy lifecycle. The app also contains Zustand state and older Express endpoints that export instrument JSON or read a strategy status file. Do not treat browser local storage or `logs/instruments_config.json` as authoritative for which Docker instruments are active; the daemon uses the Flask API for that selection.

In normal development, Vite forwards `/api/*` to Flask. The Express server has legacy instrument export/status handlers too, but those are separate routes and are not the database CRUD path. If investigating export/status behavior, verify which server a request actually reaches.

## 6. State and Persistence

The frontend uses Zustand for shared UI state. The store is configured in [`frontend-react/src/stores/app.ts`](frontend-react/src/stores/app.ts) and persists a subset under the browser local-storage key `app-store`: cached instrument data, theme, and trailing-stop preferences. The theme is also initialized from the `theme` local-storage key.

Local storage belongs to one browser profile. It is not shared across users or machines, and it is not the durable database for the strategy daemon. The Instruments page fetches its displayed configuration from Flask. Treat PostgreSQL/API responses as authoritative for the server-side instrument configuration.

The dashboard also uses files in `logs/` for account snapshots, alerts, and monitoring. These files have a different purpose from PostgreSQL instrument records: they provide data to display, while the database configures which strategies are active.

### Settings and runtime configuration

The global trailing-stop panel updates Zustand and persists the values in the current browser's local storage. The daemon has a legacy file input for `logs/instruments_config.json`: when present, it reads `trailingStopsConfig` from that file while still getting active instrument rows from Flask. The daemon currently passes the global breakeven/trailing RR values into the HD runner environment only; it does not consume the panel's global maximum-risk value. The page's claim that all three settings apply to every strategy is broader than this runtime wiring. The per-instrument maximum-risk field is a separate value and is passed to HD through the database-backed instrument configuration.

There is also an integration mismatch: the Instruments page calls the store's `exportInstruments()` method, which posts to relative `/api/instruments/export`. Vite forwards `/api/*` to Flask, but Flask does not implement that export route; the route exists on Express port `4000`. Thus the normal React/Vite request does not reliably write the JSON file consumed by the daemon. Until that request is routed to Express or replaced with a database-backed setting, do not assume saving the global panel updates a running HD strategy. By contrast, per-instrument fields such as maximum initial risk are sent through Flask and stored with the instrument configuration.

## 7. Run the Dashboard

### Docker Compose (recommended for the full application)

The dashboard depends on backend services and data sources, so Docker Compose is the simplest way to start the coordinated application when its environment is configured.

1. Install Docker Desktop and Docker Compose, and make sure PostgreSQL is running on the host. PostgreSQL is not a Compose service in this setup.
2. From the repository root, create the local environment file and configure it:

   ```sh
   cp .env.example .env
   ```

   Set `OPENALGO_API_KEY` and configure `DB_URL` for the PostgreSQL database. For the documented Docker-to-host setup, the URL format is `postgresql://USER:PASSWORD@host.docker.internal:5432/DATABASE`. Keep credentials out of source control.

3. Build and start the services:

   ```sh
   docker-compose up -d --build
   ```

4. Check service state and logs:

   ```sh
   docker-compose ps
   docker-compose logs -f react_dashboard
   ```

5. Open the React dashboard at [http://localhost:3000](http://localhost:3000). The Compose setup also exposes the Streamlit interface at [http://localhost:8502](http://localhost:8502).

Use `docker-compose down` to stop the stack. For available project shortcuts, run `make help` or inspect [`Makefile`](Makefile). Follow the repository's Docker guides for environment and database setup details.

### Run the React development server

This runs the frontend and its Express helper server; it does not by itself start PostgreSQL, Flask, or the Python strategy daemon.

1. Install a supported Node.js/npm version.
2. In a terminal, go to the frontend directory and install dependencies:

   ```sh
   cd frontend-react
   npm install
   ```

3. Start the frontend and Express server:

   ```sh
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000).

For API-backed pages to work, the Flask API must be reachable at the target configured in [`frontend-react/vite.config.ts`](frontend-react/vite.config.ts) (`API_TARGET`, defaulting to `http://host.docker.internal:5003`) and its database/integrations must be configured. In Docker Compose, `API_TARGET` is set to `http://strategy_worker:5003`. The Express helper uses port `4000`. Running only `npm run dev` is useful for frontend work, but it is not a complete trading runtime.

Useful frontend checks:

```sh
npm run type-check
npm run lint
npm run build
```

Run these from `frontend-react/`.

## 8. Ports and Requests

| Port | Service | Typical use |
| --- | --- | --- |
| `3000` | Vite / React dashboard | Browser access to the frontend. |
| `4000` | Express helper server | Selected file operations, reset operations, health check, and legacy endpoints. |
| `5003` | Flask API | Instrument database CRUD, symbols, and API-backed analytics/data. |
| `5432` | PostgreSQL on the host in this setup | Durable backend database connection; Compose does not define a PostgreSQL service. |

The browser usually makes same-origin requests to the Vite server. Vite forwards `/api` to Flask according to `API_TARGET`; in Docker the target is configured for the API service. The Vite configuration also provides development access to repository log files. Some older UI code calls the Express server explicitly for file/alert functions.

## 9. Troubleshooting

| Symptom | Check |
| --- | --- |
| Dashboard opens but API-backed pages show errors | Confirm Flask is running, its database connection works, and `API_TARGET` points to the right host/port. Inspect `docker-compose logs` for the API service. |
| Instrument changes do not appear | Refresh the Instruments page and check the Flask response and database. Confirm the record's status is active if it should run. |
| An inactive instrument still appears in Orderbook or Logs | Those pages can display broker snapshots or historical files. Check the daemon's active configuration/status separately; deactivation does not erase history or cancel broker orders. |
| Strategy does not start | Check the PostgreSQL record's status, strategy name, daemon logs, API connectivity, schedule, and required OpenAlgo configuration. |
| Strategy keeps running after deactivation | The daemon reconciles periodically. Check the next daemon poll and its logs. Separately inspect and manage any broker orders or open positions. |
| Dashboard or positions show no current values | Check whether `logs/dashboard_data.json` is being generated and updated. Wallet values may depend on `logs/wallet_data.json`. |
| Logs or alerts are empty | Check that the expected dated CSV/JSON files exist under `logs/`, and that the frontend can retrieve them. Some views expect files for the current date. |
| Port is already in use | Stop the conflicting local service or change the relevant service configuration before starting another copy. |

## 10. Relevant Source Files

| File | What it owns |
| --- | --- |
| [`frontend-react/src/App.tsx`](frontend-react/src/App.tsx) | Browser routes and app-level providers. |
| [`frontend-react/src/pages/`](frontend-react/src/pages/) | Dashboard page components. |
| [`frontend-react/src/hooks/useInstruments.ts`](frontend-react/src/hooks/useInstruments.ts) | Instrument API requests and response mapping. |
| [`frontend-react/src/hooks/useData.ts`](frontend-react/src/hooks/useData.ts) | Account snapshot and analytics data hooks. |
| [`frontend-react/src/stores/app.ts`](frontend-react/src/stores/app.ts) | Zustand state and local-storage persistence. |
| [`frontend-react/vite.config.ts`](frontend-react/vite.config.ts) | Development server, API proxy, and log-file access. |
| [`frontend-react/server.js`](frontend-react/server.js) | Express file/reset helpers and older compatibility routes. |
| [`api_server.py`](api_server.py) | Flask API, including instrument routes. |
| [`core/db_models.py`](core/db_models.py) | SQLAlchemy database models. |
| [`strategy_daemon.py`](strategy_daemon.py) | Active-instrument polling and strategy process management. |
| [`run_strategy.py`](run_strategy.py) | Strategy runner entry point and strategy registration. |
| [`docker-compose.yml`](docker-compose.yml) | Container services, networks, and runtime wiring. |

## 11. Operational Safety

- Verify each instrument's status, strategy, broker symbol, schedule, lot sizing, and risk settings before activation.
- Confirm whether the configured OpenAlgo mode is live or analyzer/paper before running strategies.
- Deactivation controls future daemon-managed execution; it is not a broker-side cancel or position-close command.
- Keep API keys and broker credentials in local environment or secret-management configuration. Do not commit them to this repository.
- Treat logs and dashboard snapshots as operational evidence, not as proof that an order is currently open or that a strategy process is still running. Confirm order/position state with the broker-facing system.