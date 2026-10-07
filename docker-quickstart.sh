#!/bin/bash

# Quick Start Script for Trading Strategy Docker Setup
# This script helps you get started with the Docker environment

set -e  # Exit on error

echo "════════════════════════════════════════════════════════════════"
echo "  Trading Strategy - Docker Quick Start Setup"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "✅ Docker found: $(docker --version)"

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install it first."
    echo "   Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker Compose found: $(docker-compose --version)"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ .env file created. Please edit it with your configuration."
    else
        echo "⚠️  .env.example not found. Creating basic .env..."
        cat > .env << 'EOF'
# Strategy Settings
STRATEGY=ema21
MODE=live
SCRIPT=NIFTY

# OpenAlgo Configuration
OPENALGO_HOST=http://host.docker.internal:5002
OPENALGO_WS_URL=ws://host.docker.internal:8766
WEBSOCKET_HOST=host.docker.internal
WEBSOCKET_PORT=8766

# Timezone
TZ=Asia/Kolkata
EOF
        echo "✅ Basic .env file created."
    fi
else
    echo "✅ .env file already exists."
fi

echo ""
echo "📁 Checking directories..."

# Create logs directory if it doesn't exist
if [ ! -d logs ]; then
    echo "📝 Creating logs directory..."
    mkdir -p logs
    chmod 755 logs
    echo "✅ logs directory created."
else
    echo "✅ logs directory exists."
fi

# Create data directory if it doesn't exist
if [ ! -d data ]; then
    echo "📝 Creating data directory..."
    mkdir -p data
    chmod 755 data
    echo "✅ data directory created."
else
    echo "✅ data directory exists."
fi

echo ""
echo "🔨 Building Docker images..."
echo "   (This may take a few minutes on first run)"
echo ""

docker-compose build

echo ""
echo "✅ Docker images built successfully!"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "  Setup Complete! Here's what you can do next:"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🚀 Start All Services:"
echo "   docker-compose up -d"
echo ""
echo "📊 Access Dashboards:"
echo "   • React Dashboard:   http://localhost:3000"
echo "   • Streamlit:         http://localhost:8502"
echo ""
echo "📈 Run a Backtest:"
echo "   make backtest STRATEGY=ema21"
echo ""
echo "🔍 View Logs:"
echo "   docker-compose logs -f strategy_worker"
echo ""
echo "💻 Open Shell in Container:"
echo "   docker-compose exec strategy_worker bash"
echo ""
echo "⏹️  Stop All Services:"
echo "   docker-compose down"
echo ""
echo "📚 For More Commands:"
echo "   make help"
echo ""
echo "📖 Read Full Documentation:"
echo "   cat DOCKER_GUIDE.md"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
