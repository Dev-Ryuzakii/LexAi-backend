#!/bin/bash

# AI-CBT API Platform Startup Script

echo "🚀 Starting AI-CBT API Platform..."

# Check if Redis is running
if ! command -v redis-cli &> /dev/null
then
    echo "❌ Redis CLI could not be found. Please install Redis."
    exit 1
fi

# Start Redis in background if not already running
if ! redis-cli ping &> /dev/null
then
    echo "🔄 Starting Redis server..."
    redis-server --daemonize yes
    sleep 2
fi

# Check if Redis is now running
if redis-cli ping &> /dev/null
then
    echo "✅ Redis is running"
else
    echo "❌ Failed to start Redis"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🔄 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "🔄 Installing dependencies..."
    pip install -r requirements.txt
    echo "🔄 Installing Alembic for database migrations..."
    pip install alembic
else
    echo "✅ Virtual environment found"
    source venv/bin/activate
fi

# Create necessary directories
mkdir -p logs
mkdir -p data

# Run database migrations
echo "🔄 Running database migrations..."
python src/migrate_db.py

# Check if migrations were successful
echo "🔄 Starting AI-CBT API Platform..."
echo "📖 API Documentation: http://localhost:5001/api/v1/docs/"
echo "🌐 Main Platform: http://localhost:5001/"

# Start the application
python src/app_api.py