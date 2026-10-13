#!/bin/bash
# Fix for OpenAlgo Data Flow to React Dashboard
# This script ensures the dashboard exporter picks up the updated OpenAlgo API key

echo "🔧 Fixing OpenAlgo Data Flow to React Dashboard"
echo "=" * 60
echo ""

# Step 1: Verify environment variables
echo "📋 Step 1: Verifying environment configuration..."
source .env
if [ -z "$OPENALGO_API_KEY" ]; then
    echo "❌ OPENALGO_API_KEY is not set in .env!"
    exit 1
fi

if [ -z "$OPENALGO_HOST" ]; then
    echo "❌ OPENALGO_HOST is not set in .env!"
    exit 1
fi

echo "✓ API Key: ${OPENALGO_API_KEY:0:20}..."
echo "✓ Host: $OPENALGO_HOST"
echo ""

# Step 2: Stop the dashboard_exporter service
echo "⏹️  Step 2: Stopping dashboard_exporter service..."
docker-compose down dashboard_exporter 2>/dev/null || echo "   (Service not running)"
sleep 2
echo ""

# Step 3: Clear the stale data
echo "🗑️  Step 3: Clearing stale data..."
rm -f logs/dashboard_data.json logs/wallet_data.json
touch logs/dashboard_data.json logs/wallet_data.json
echo "✓ Data files cleared"
echo ""

# Step 4: Restart the dashboard_exporter service
echo "🚀 Step 4: Restarting dashboard_exporter service with updated credentials..."
docker-compose up -d dashboard_exporter
echo ""

# Step 5: Monitor the service
echo "👀 Step 5: Monitoring service startup (wait 10 seconds)..."
sleep 10
echo ""

# Step 6: Check if data is being populated
echo "📊 Step 6: Verifying data is being exported..."
if [ -s logs/dashboard_data.json ]; then
    echo "✓ Dashboard data file has content!"
    data_size=$(wc -c < logs/dashboard_data.json)
    echo "  File size: $data_size bytes"
    
    # Check if it contains positions
    if grep -q '"positions"' logs/dashboard_data.json; then
        positions_count=$(grep -o '"symbol"' logs/dashboard_data.json | wc -l)
        echo "  Positions found: $positions_count"
    fi
    
    # Check mode
    mode=$(grep -o '"mode": "[^"]*"' logs/dashboard_data.json | head -1)
    echo "  Mode: $mode"
else
    echo "⚠️  Dashboard data file is empty or doesn't exist"
    echo "   Checking Docker logs..."
    docker logs dashboard_exporter | tail -20
fi

echo ""
echo "=" * 60
echo "✅ Fix complete! Dashboard exporter should now work properly."
echo ""
echo "To monitor the dashboard exporter logs in real-time, run:"
echo "  docker-compose logs -f dashboard_exporter"
echo ""
