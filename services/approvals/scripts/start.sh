#!/bin/bash
# Start the Approvals service

set -e

echo "🚀 Starting Anumate Approvals Service"

# Set environment variables
export ANUMATE_ENV=${ANUMATE_ENV:-development}
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8004}
export DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://anumate:anumate@localhost:5432/anumate_approvals}

# Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

echo "Environment: $ANUMATE_ENV"
echo "Host: $HOST"
echo "Port: $PORT"
echo "Database: $DATABASE_URL"

# Install dependencies if needed
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

echo "📦 Installing dependencies..."
source .venv/bin/activate
pip install -e .

# Initialize database
echo "🗄️ Initializing database..."
python -c "
import asyncio
from config.database import init_db
asyncio.run(init_db())
print('Database initialized successfully')
"

# Start the service
echo "🌟 Starting Approvals service..."
python -m uvicorn api.main:app --host $HOST --port $PORT --reload
