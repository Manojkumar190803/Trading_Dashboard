# Docker Guide

This guide describes the current Compose configuration in
[`docker-compose.yml`](docker-compose.yml). It replaces older Docker setup,
architecture, quick-reference, persistence, and fix notes.

## Prerequisites

- Docker Engine/Desktop with the `docker compose` command.
- A PostgreSQL instance reachable from Docker. PostgreSQL is **not** a
  service in this Compose stack.
- An OpenAlgo service reachable from Docker.
- A local `.env` containing the database URL and OpenAlgo credentials/settings
  used by the services. Keep credentials local; do not commit them.

Docker Desktop containers reach host services through `host.docker.internal`.
Configure the Docker-facing OpenAlgo REST host and ensure the websocket URL
points to the same OpenAlgo instance.

## Start and Stop

From the repository root:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Open the React dashboard at [http://localhost:3000](http://localhost:3000).
Stop the services with:

```sh
docker compose down
```

The Compose file bind-mounts `./logs` and `./data` from the host, so those
directories remain after `docker compose down`. Back them up as needed before
manually removing or replacing their contents.

## Current Services

| Service | Purpose | Host port |
| --- | --- | --- |
| `react_dashboard` | React/Vite frontend and Express helpers/SSE | `3000`, `4000` |
| `strategy_worker` | Flask API and strategy CLI utilities; does not launch a fixed live strategy | `5003` |
| `strategy_daemon` | Polls active dashboard instruments and manages one strategy process per instrument | Internal |
| `dashboard_exporter` | Fetches OpenAlgo account snapshots and writes dashboard data | Internal |

There is no PostgreSQL or Streamlit service in the current
`docker-compose.yml`; older notes that describe either as a current Compose
service are stale.

The React container proxies `/api/*` to Flask using `API_TARGET`. The daemon
uses `STRATEGY_DASHBOARD_API_URL` to read active database-backed instruments.
It reconciles instrument settings approximately every five seconds. Only
`ACTIVE` records are managed. Manual `run_strategy.py --mode live` commands
bypass dashboard activation/status.

Deactivating an instrument stops its managed runner at reconciliation, but
does not cancel an order already accepted by OpenAlgo or close an open broker
position. Check and manage those broker-side states separately.

## Data and Persistence

The strategy worker, daemon, and exporter share:

| Host directory | Container directory | Use |
| --- | --- | --- |
| `./logs` | `/app/logs` | Account snapshots, strategy logs, alerts, monitoring, and analytics data |
| `./data` | `/app/data` | Strategy state and cached/backtest data |

The React service also mounts `frontend-react/src`, `frontend-react/public`,
and `logs` for local dashboard development and file access. The override file
[`docker-compose.override.yml`](docker-compose.override.yml) adds source mounts
and debug logging for development. `docker-compose.yml` defines the production
service topology and ports.

The exporter writes `logs/dashboard_data.json`. It takes a full snapshot every
120 seconds while flat, every 30 seconds while a position is active, refreshes
after order fills, and applies active-position LTP websocket updates. Express
streams snapshot changes to the Dashboard page. Positions and Orderbook read
the shared snapshot file directly.

## Useful Commands

```sh
# Inspect service state
docker compose ps

# Follow one service
docker compose logs -f strategy_worker
docker compose logs -f strategy_daemon
docker compose logs -f dashboard_exporter
docker compose logs -f react_dashboard

# Restart/recreate after environment changes
docker compose up -d --force-recreate dashboard_exporter

# Run a one-off backtest
docker compose exec strategy_worker python3 run_strategy.py \
  --script NIFTY --strategy ema21 --mode backtest \
  --start 2026-10-01 --end 2026-10-06

# Inspect daemon-managed status
cat logs/strategies_status.json
```

If changing `.env` values used by other containers, recreate those services as
well; running containers do not reload their environment automatically.
Dashboard instrument edits are read from the database by the daemon and passed
to that instrument's strategy process; they do not require editing `.env`.

For strategy syntax, supported instruments, and strategy-specific controls,
see the relevant specification in [`docs/`](docs/). For dashboard page and
data details, see [DASHBOARD.md](DASHBOARD.md).

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| A service exits or is unhealthy | Run `docker compose ps` and inspect `docker compose logs <service>`. |
| Dashboard opens but API calls fail | Check `strategy_worker`, PostgreSQL connectivity, and `API_TARGET`. |
| Dashboard account data is stale | Check `dashboard_exporter`, OpenAlgo REST/websocket connectivity, and `logs/dashboard_data.json`. |
| An active instrument has no runner | Confirm its PostgreSQL status is `ACTIVE`; inspect `strategy_daemon` logs and `logs/strategies_status.json`. |
| Port conflict | Check whether ports `3000`, `4000`, or `5003` are already used before starting Compose. |
| Logs are missing | Check host `./logs` permissions and whether the expected dated file has been produced. |

Never infer that a position or order is closed solely from a dashboard
snapshot or a stopped strategy container; verify the broker state.
