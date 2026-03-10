#!/bin/bash
# Project Dashboard Launcher

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PROJECT_NAME="PRD: OpenClaw – Sportsbook + Prediction Market Arbitrage Hunter"

echo "📊 Starting $PROJECT_NAME Dashboard..."

# Check if Node.js is available
if command -v node &> /dev/null; then
    echo "Starting server on http://localhost:${PORT:-3456}"
    node dashboard-server.js
else
    echo "⚠️  Node.js not found. Opening dashboard.html directly in browser..."
    
    # Try to open in default browser
    if command -v xdg-open &> /dev/null; then
        xdg-open dashboard.html
    elif command -v open &> /dev/null; then
        open dashboard.html
    elif command -v start &> /dev/null; then
        start dashboard.html
    else
        echo "Please open dashboard.html manually in your browser"
    fi
fi
