# Docker Guide for Trading Strategy Application

## Current Compose Runtime

In the current Compose deployment, `strategy_worker` serves the Flask API only.
The legacy-named `hd_strategy_daemon` polls `GET /api/instruments` every five
seconds and starts strategy runners only for `ACTIVE` dashboard instruments;
inactive and archived rows are excluded. Compose clears `STRATEGY_FILTER`, so
the daemon can run every configured strategy type. See
[DOCKER_ARCHITECTURE.md](DOCKER_ARCHITECTURE.md) for service and data flow.

Deactivation stops a strategy process on the next daemon poll and prevents
future signals from it. It does not cancel an order already submitted to
OpenAlgo or close a broker position; check and manage those broker-side states
separately. Manual `run_strategy.py --mode live` commands bypass dashboard
instrument status.

The API initializes the schema on startup, including additive updates for
missing `instruments.entry_cutoff_time` and `instruments.max_initial_risk_points`
columns. Instrument API sessions are closed on every path and failed writes are
rolled back. The React health check probes `127.0.0.1:3000` inside the container.

## Overview

This guide explains how to run the trading strategy application using Docker. The setup includes:

- **React Dashboard** (Modern Frontend) - Port 3000
- **Streamlit Dashboard** (Legacy Frontend) - Port 8502
- **Strategy Worker** - Flask API on port 5003
- **Strategy Daemon** - Starts live runners from active dashboard instruments
- **Dashboard Exporter** - Writes broker account data to shared JSON files

## Prerequisites

- Docker & Docker Compose installed
- `.env` file configured with your credentials
- Trading logs directory at `./logs/`

## Quick Start

### Build and Start All Services

```bash
# Build images (first time only)
docker-compose build

# Start all services in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### Access the Application

- **React Dashboard**: http://localhost:3000
- **Streamlit Dashboard**: http://localhost:8502
- **Logs Directory**: http://localhost:3000/logs

## Individual Services

### React Dashboard (Modern UI)

```bash
# Start only the React dashboard
docker-compose up -d react_dashboard

# View logs
docker-compose logs -f react_dashboard
```

**Features:**
- Professional dark theme
- Real-time metrics
- Trading positions, orders, analytics
- System logs viewer
- Responsive design

**Port**: 3000

### Strategy Worker (API and CLI Utilities)

```bash
# Start the API worker
docker-compose up -d strategy_worker

# View API logs
docker-compose logs -f strategy_worker

# Run a one-off backtest (independent of dashboard instrument status)
docker compose exec strategy_worker python3 run_strategy.py \
  --script NIFTY --strategy ema21 --mode backtest \
  --start 2026-10-01 --end 2026-10-06
```

Use the dashboard-managed daemon for live Docker trading. A manually started
`run_strategy.py --mode live` process does not enforce dashboard instrument
status.

### Streamlit Dashboard (Legacy UI)

```bash
# Start Streamlit dashboard
docker-compose up -d streamlit_interface

# Access at: http://localhost:8502
docker-compose logs -f streamlit_interface
```

## Environment Configuration

### Create `.env` File

```bash
cp .env.example .env
```

### Edit `.env` with Your Configuration

```ini
# Strategy Settings
STRATEGY=ema21              # Strategy name (ema21, 2bc, hd, etc.)
MODE=live                   # live, backtest, paper
SCRIPT=NIFTY               # Index/Script to trade

# OpenAlgo Configuration
OPENALGO_HOST=http://host.docker.internal:5002
OPENALGO_WS_URL=ws://host.docker.internal:8766
WEBSOCKET_HOST=host.docker.internal
WEBSOCKET_PORT=8766

# Timezone
TZ=Asia/Kolkata

# Optional: API Keys
API_KEY=your_key_here
API_SECRET=your_secret_here
```

## Running Backtests in Docker

### Using docker-compose

```bash
# Run single backtest
docker-compose run --rm strategy_worker \
  --mode backtest \
  --start 2026-10-01 \
  --end 2026-10-06

# Run specific strategy backtest
docker-compose run --rm strategy_worker \
  -e STRATEGY=2bc \
  -e SCRIPT=NIFTY \
  --mode backtest
```

### Using Dockerfile.backtest

```bash
# Build backtest image
docker build -f Dockerfile.backtest -t strategy-backtest .

# Run backtest
docker run --rm \
  -v $(pwd)/logs:/app/logs \
  -e STRATEGY=ema21 \
  -e SCRIPT=NIFTY \
  -e START_DATE=2026-10-01 \
  -e END_DATE=2026-10-06 \
  strategy-backtest
```

## Docker Compose Commands

### View Running Services

```bash
# List all running containers
docker-compose ps

# Show detailed status
docker-compose ps -a
```

### View Logs

```bash
# View all logs
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# View specific service logs
docker-compose logs -f strategy_worker

# Last 50 lines
docker-compose logs --tail 50 react_dashboard
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart strategy_worker

# Hard restart (stop + start)
docker-compose down
docker-compose up -d
```

### Clean Up

```bash
# Stop all services
docker-compose stop

# Remove all containers and networks
docker-compose down

# Remove images too
docker-compose down --rmi all

# Remove volumes (logs/data will be deleted)
docker-compose down -v
```

## Development Mode

### Using docker-compose.override.yml

Create `docker-compose.override.yml` for local development:

```yaml
version: '3.8'

services:
  strategy_worker:
    environment:
      LOG_LEVEL: DEBUG
      PYTHONUNBUFFERED: 1
    volumes:
      - ./core:/app/core
      - ./strategies:/app/strategies
      - ./run_strategy.py:/app/run_strategy.py
    restart: on-failure

  react_dashboard:
    volumes:
      - ./frontend-react/dist:/usr/share/nginx/html
    restart: on-failure
```

Then run with development settings:

```bash
docker-compose up
```

## Volume Mounts

The application uses the following volumes:

| Volume | Purpose | Mounted Path |
|--------|---------|--------------|
| `./logs` | Trading logs & alerts | `/app/logs` |
| `./data` | Backtest data | `/app/data` |
| `./frontend-react/dist` | React build | `/usr/share/nginx/html` |

### Verify Volumes

```bash
# Check volumes
docker-compose exec strategy_worker ls -la /app/logs

# Access logs from host
ls -la ./logs/
```

## Networking

Services communicate via the Docker internal network:

- `strategy_worker` - Core engine
- `streamlit_interface` - Streamlit app
- `react_dashboard` - Nginx + React
- `host.docker.internal` - Host machine access

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs strategy_worker

# Verify env variables
docker-compose config

# Rebuild image
docker-compose build --no-cache strategy_worker
```

### Port Already in Use

```bash
# Check what's using port 3000
lsof -i :3000

# Use different port in docker-compose
docker-compose -f docker-compose.yml -p new_port up -d
```

### Logs Directory Permissions

```bash
# Fix log directory permissions
chmod -R 755 ./logs

# Run container with specific user
docker-compose exec strategy_worker chown -R nobody:nogroup /app/logs
```

### WebSocket Connection Issues

```bash
# Check if host.docker.internal is resolvable
docker-compose exec strategy_worker ping host.docker.internal

# Verify ports on host
netstat -an | grep 8766
```

## Performance Tuning

### Increase Resource Limits

Edit `docker-compose.yml`:

```yaml
services:
  strategy_worker:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Enable Performance Monitoring

```bash
# Monitor resource usage
docker stats

# CPU usage over time
docker stats --no-stream strategy_worker
```

## Production Deployment

### Using Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml trading_strategy
```

### Using Kubernetes

Create `k8s/` directory with manifests:

```bash
# Apply manifests
kubectl apply -f k8s/
```

## Updating the Application

```bash
# Pull latest code
git pull

# Rebuild images
docker-compose build --no-cache

# Restart services
docker-compose up -d
```

## Monitoring & Health Checks

### Health Status

```bash
# Check service health
docker-compose ps

# Manual health check
docker exec strategy_worker curl -f http://localhost:8501/healthz
```

### Log Aggregation

```bash
# Export logs to file
docker-compose logs > container_logs.txt

# Filter logs
docker-compose logs strategy_worker | grep ERROR
```

## Advanced Usage

### Running Custom Commands

```bash
# Execute command in container
docker-compose exec strategy_worker python3 run_strategy.py --help

# Run bash in container
docker-compose exec strategy_worker bash
```

### Multiple Strategies in Parallel

```bash
# Create separate compose files
docker-compose -f docker-compose.yml \
               -f docker-compose.ema21.yml \
               -f docker-compose.2bc.yml \
               up -d
```

### Persistent Strategy Instances

Update `docker-compose.yml`:

```yaml
services:
  strategy_ema21:
    extends:
      service: strategy_worker
    container_name: strategy_ema21
    environment:
      STRATEGY: ema21

  strategy_2bc:
    extends:
      service: strategy_worker
    container_name: strategy_2bc
    environment:
      STRATEGY: 2bc
```

Then run:

```bash
docker-compose up -d strategy_ema21 strategy_2bc
```

## Support & Documentation

- **React Dashboard**: See `frontend-react/README.md`
- **Strategy Code**: See `core/` and `strategies/` directories
- **Streamlit App**: See `frontend/` directory

## License

See LICENSE file in root directory.
