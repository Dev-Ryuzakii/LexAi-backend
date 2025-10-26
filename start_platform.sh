#!/bin/bash

# AI-CBT Platform Startup Script
echo "🚀 Starting AI-CBT Platform..."
echo "=================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found. Creating one..."
    python -m venv venv
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Change to src directory
cd src

echo "=================================="
echo "🌐 Starting Services..."
echo "=================================="

# Start API service in background
echo "🔧 Starting API Service (Port 5001)..."
python app_api.py &
API_PID=$!

# Wait a moment for API service to start
sleep 3

echo "=================================="
echo "✅ AI-CBT Platform is now running!"
echo "=================================="
echo "🌐 Main API Platform: http://localhost:5001/"
echo "📖 API Documentation: http://localhost:5001/api/v1/docs"
echo "🔧 Interactive Dashboard: http://localhost:5001/api-dashboard"
echo "=================================="
echo "Press Ctrl+C to stop all services"

# Function to clean up background processes
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $API_PID 2>/dev/null
    echo "✅ All services stopped."
    exit 0
}

# Trap Ctrl+C and run cleanup
trap cleanup SIGINT

# Wait for background processes
wait