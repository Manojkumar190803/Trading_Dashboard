.PHONY: help build up down logs restart clean test backtest shell

DOCKER_COMPOSE := docker-compose
STRATEGY ?= ema21
SCRIPT ?= NIFTY
MODE ?= live
START_DATE ?= 2026-10-01
END_DATE ?= 2026-10-06

help:
	@echo "Trading Strategy Docker Commands"
	@echo "================================="
	@echo ""
	@echo "Build:"
	@echo "  make build              Build all Docker images"
	@echo "  make build-backtest     Build backtest image"
	@echo ""
	@echo "Running:"
	@echo "  make up                 Start all services"
	@echo "  make down               Stop all services"
	@echo "  make restart            Restart all services"
	@echo "  make status             Show service status"
	@echo ""
	@echo "Development:"
	@echo "  make dev                Start in development mode"
	@echo "  make shell              Open shell in strategy_worker"
	@echo "  make logs               Follow all logs"
	@echo "  make logs-strategy      Follow strategy worker logs"
	@echo "  make logs-streamlit     Follow streamlit logs"
	@echo "  make logs-react         Follow react dashboard logs"
	@echo ""
	@echo "Strategy Execution:"
	@echo "  make backtest           Run backtest"
	@echo "  make backtest-ema21     Backtest EMA21 strategy"
	@echo "  make backtest-2bc       Backtest 2BC strategy"
	@echo "  make live               Run in live mode"
	@echo "  make paper              Run in paper trading mode"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean              Remove all containers and volumes"
	@echo "  make test               Run tests in container"
	@echo "  make lint               Run linting"
	@echo "  make exec CMD=<cmd>     Execute command in strategy_worker"
	@echo ""
	@echo "Environment Variables:"
	@echo "  STRATEGY={ema21,2bc,hd,tc,etc}  (default: ema21)"
	@echo "  SCRIPT={NIFTY,BANKNIFTY,etc}    (default: NIFTY)"
	@echo "  MODE={live,backtest,paper}      (default: live)"
	@echo "  START_DATE=YYYY-MM-DD           (default: 2026-10-01)"
	@echo "  END_DATE=YYYY-MM-DD             (default: 2026-10-06)"
	@echo ""

build:
	@echo "Building Docker images..."
	$(DOCKER_COMPOSE) build

build-backtest:
	@echo "Building backtest image..."
	docker build -f Dockerfile.backtest -t strategy-backtest .

up:
	@echo "Starting all services..."
	$(DOCKER_COMPOSE) up -d
	@echo "Services started. Access dashboard at:"
	@echo "  React:     http://localhost:3000"
	@echo "  Streamlit: http://localhost:8502"

down:
	@echo "Stopping all services..."
	$(DOCKER_COMPOSE) down

restart:
	@echo "Restarting all services..."
	$(DOCKER_COMPOSE) restart

status:
	@echo "Service Status:"
	$(DOCKER_COMPOSE) ps

dev:
	@echo "Starting in development mode..."
	$(DOCKER_COMPOSE) up

logs:
	@echo "Following all logs..."
	$(DOCKER_COMPOSE) logs -f

logs-strategy:
	$(DOCKER_COMPOSE) logs -f strategy_worker

logs-streamlit:
	$(DOCKER_COMPOSE) logs -f streamlit_interface

logs-react:
	$(DOCKER_COMPOSE) logs -f react_dashboard

shell:
	@echo "Opening shell in strategy_worker..."
	$(DOCKER_COMPOSE) exec strategy_worker bash

backtest:
	@echo "Running backtest (Strategy: $(STRATEGY), Script: $(SCRIPT), Period: $(START_DATE) to $(END_DATE))..."
	$(DOCKER_COMPOSE) run --rm strategy_worker \
		-e STRATEGY=$(STRATEGY) \
		-e SCRIPT=$(SCRIPT) \
		-e MODE=backtest \
		-e START_DATE=$(START_DATE) \
		-e END_DATE=$(END_DATE)

backtest-ema21:
	@echo "Running EMA21 backtest..."
	make backtest STRATEGY=ema21

backtest-2bc:
	@echo "Running 2BC backtest..."
	make backtest STRATEGY=2bc

live:
	@echo "Starting live trading (Strategy: $(STRATEGY), Script: $(SCRIPT))..."
	$(DOCKER_COMPOSE) run --rm strategy_worker \
		-e STRATEGY=$(STRATEGY) \
		-e SCRIPT=$(SCRIPT) \
		-e MODE=live

paper:
	@echo "Starting paper trading (Strategy: $(STRATEGY), Script: $(SCRIPT))..."
	$(DOCKER_COMPOSE) run --rm strategy_worker \
		-e STRATEGY=$(STRATEGY) \
		-e SCRIPT=$(SCRIPT) \
		-e MODE=paper

test:
	@echo "Running tests..."
	$(DOCKER_COMPOSE) exec strategy_worker pytest -v

lint:
	@echo "Running linting..."
	$(DOCKER_COMPOSE) exec strategy_worker flake8 .

exec:
	@echo "Executing command in strategy_worker..."
	$(DOCKER_COMPOSE) exec strategy_worker $(CMD)

clean:
	@echo "Cleaning up containers and volumes..."
	$(DOCKER_COMPOSE) down -v
	@echo "Cleanup complete"

inspect:
	@echo "Inspecting strategy_worker container..."
	docker inspect strategy_worker

push:
	@echo "Pushing images to registry (set REGISTRY env var)"
	docker-compose push

pull:
	@echo "Pulling images from registry (set REGISTRY env var)"
	docker-compose pull

ps:
	@echo "Process list:"
	$(DOCKER_COMPOSE) ps

prune:
	@echo "Pruning unused Docker resources..."
	docker container prune -f
	docker image prune -f
	docker network prune -f
	docker volume prune -f

version:
	@echo "Docker Compose version:"
	$(DOCKER_COMPOSE) version

config:
	@echo "Docker Compose configuration:"
	$(DOCKER_COMPOSE) config
