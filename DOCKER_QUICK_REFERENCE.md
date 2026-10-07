# Docker Quick Reference Guide

## One-Liner Startup

```bash
# Full setup: build images, start services, open dashboards
./docker-quickstart.sh && docker-compose up -d
```

## Essential Commands

### 🚀 Start/Stop

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart services
docker-compose restart
```

### 📊 Access Dashboards

| Dashboard | URL | Port |
|-----------|-----|------|
| React Dashboard | http://localhost:3000 | 3000 |
| Streamlit Dashboard | http://localhost:8502 | 8502 |
| Logs Directory | http://localhost:3000/logs | 3000 |

### 📈 Run Strategies

```bash
# Run backtest
make backtest STRATEGY=ema21 START_DATE=2026-10-01 END_DATE=2026-10-06

# Run live trading
make live STRATEGY=ema21 SCRIPT=NIFTY

# Run paper trading
make paper STRATEGY=2bc SCRIPT=BANKNIFTY

# Run specific strategy backtest
make backtest-ema21
make backtest-2bc
```

### 🔍 View Logs

```bash
# All logs
docker-compose logs -f

# Strategy worker only
docker-compose logs -f strategy_worker

# Streamlit only
docker-compose logs -f streamlit_interface

# React dashboard only
docker-compose logs -f react_dashboard

# Last 50 lines
docker-compose logs --tail 50 strategy_worker

# Search in logs
docker-compose logs | grep ERROR
```

### 💻 Container Access

```bash
# Open bash shell
docker-compose exec strategy_worker bash

# Run command directly
docker-compose exec strategy_worker python3 run_strategy.py --help

# Execute arbitrary command
make exec CMD="ls -la /app/logs"
```

### 📋 Service Status

```bash
# List running containers
docker-compose ps

# Detailed status
docker-compose ps -a

# Service statistics
docker stats

# Inspect service config
docker-compose config
```

## Advanced Scenarios

### Multiple Strategies in Parallel

```bash
# Run EMA21 and 2BC backtests simultaneously
docker-compose run --rm strategy_worker \
  -e STRATEGY=ema21 --detach
docker-compose run --rm strategy_worker \
  -e STRATEGY=2bc --detach
```

### Mount Local Code for Development

```bash
# Volume mounts are in docker-compose.override.yml
# Start with development settings
docker-compose up

# Changes to ./core and ./strategies reflect immediately
```

### Run Tests

```bash
make test
```

### Lint Code

```bash
make lint
```

## Troubleshooting

### Service Won't Start

```bash
# Check detailed logs
docker-compose logs strategy_worker | head -100

# Rebuild image
docker-compose build --no-cache strategy_worker

# Start with verbose output
docker-compose up strategy_worker  # Don't use -d
```

### Port Already in Use

```bash
# Find what's using port 3000
lsof -i :3000

# Kill the process
kill -9 <PID>

# Or use different port
docker-compose -p myproject up -d
```

### Permission Denied on Logs

```bash
# Fix log directory permissions
chmod -R 755 ./logs
chmod -R 755 ./data
```

### WebSocket Connection Failed

```bash
# Check connectivity to host
docker-compose exec strategy_worker ping host.docker.internal

# Verify ports are open on host
netstat -an | grep 8766
netstat -an | grep 5002
```

## Environment Variables

### Common Configurations

```bash
# EMA21 Live Trading on NIFTY
docker-compose run --rm strategy_worker \
  -e STRATEGY=ema21 \
  -e SCRIPT=NIFTY \
  -e MODE=live

# 2BC Backtest on BANKNIFTY
docker-compose run --rm strategy_worker \
  -e STRATEGY=2bc \
  -e SCRIPT=BANKNIFTY \
  -e MODE=backtest \
  -e START_DATE=2026-09-01 \
  -e END_DATE=2026-09-30

# Custom OpenAlgo Host
docker-compose run --rm strategy_worker \
  -e OPENALGO_HOST=http://custom-host:5002 \
  -e MODE=paper
```

## Performance Tuning

```bash
# Increase memory limit for strategy_worker
# Edit docker-compose.yml:
# strategy_worker:
#   deploy:
#     resources:
#       limits:
#         memory: 2G

# Monitor resource usage
docker stats strategy_worker

# Check container size
docker ps --size

# Prune unused resources
make prune
```

## Backup & Restore

### Backup Logs

```bash
# Backup all logs
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/

# Backup specific date
tar -czf logs_backup_20261006.tar.gz logs/monitoring_20261006.csv logs/trade_alerts_20261006.csv
```

### Restore Logs

```bash
# Restore from backup
tar -xzf logs_backup_$(date +%Y%m%d).tar.gz

# Merge with existing logs
tar -xzf logs_backup_20261006.tar.gz --strip-components=1 -C logs/
```

## Update & Maintenance

### Update Images

```bash
# Pull latest code
git pull

# Rebuild images
docker-compose build

# Start with fresh build
docker-compose up -d --build
```

### Clean Old Containers

```bash
# Remove stopped containers
docker container prune -f

# Remove dangling images
docker image prune -f

# Remove unused volumes
docker volume prune -f

# Remove everything (careful!)
docker system prune -a
```

## Documentation Files

| File | Purpose |
|------|---------|
| `DOCKER_GUIDE.md` | Comprehensive Docker guide |
| `docker-compose.yml` | Service configuration |
| `docker-compose.override.yml` | Development overrides |
| `Dockerfile` | Production build for strategy |
| `Dockerfile.backtest` | Backtest-specific build |
| `Dockerfile.streamlit` | Streamlit frontend |
| `nginx.conf` | React dashboard reverse proxy |
| `Makefile` | Convenient command shortcuts |

## Keyboard Shortcuts

| Action | Command |
|--------|---------|
| Follow all logs | `docker-compose logs -f` |
| Stop current logs | `Ctrl+C` |
| Exit container shell | `exit` or `Ctrl+D` |
| Open another terminal | `Cmd+T` (Mac) or `Ctrl+Alt+T` (Linux) |

## Getting Help

```bash
# List all available make commands
make help

# Show docker-compose help
docker-compose --help

# Show specific command help
docker-compose COMMAND --help

# Read full documentation
cat DOCKER_GUIDE.md
```

---

**Last Updated**: 2026-10-06
**Docker Compose Version**: 3.8
**Python Version**: 3.11
**Node Version**: 18 (React build)
