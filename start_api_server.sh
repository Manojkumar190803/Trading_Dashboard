#!/bin/bash

# Start Flask API server for symbol search and dashboard data
# This server runs on port 4000 and serves the /api/symbols/search endpoint

echo "🚀 Starting OpenAlgo API Server on port 4000..."
echo ""
echo "The server will:"
echo "  - Accept symbol search requests at: http://localhost:4000/api/symbols/search?q=NIFTY"
echo "  - Serve dashboard data JSON files"
echo "  - Enable CORS for React communication"
echo ""
echo "To stop the server, press Ctrl+C"
echo ""

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run the Flask server
python api_server.py
