#!/bin/bash
set -e

echo "🚀 Deploying Receipt Service to production..."

# Check if environment file exists
if [ ! -f .env.production ]; then
    echo "❌ .env.production file not found!"
    echo "Please copy .env.production.template to .env.production and configure it"
    exit 1
fi

# Load environment variables
export $(cat .env.production | grep -v '#' | awk '/=/ {print $1}')

# Deploy using docker-compose
docker-compose -f docker-compose.production.yml up -d

# Wait for service to be ready
echo "⏳ Waiting for service to be ready..."
timeout 60 bash -c 'until curl -f http://localhost:8001/; do sleep 2; done'

echo "✅ Receipt Service deployed successfully!"
echo "📋 Service available at: http://localhost:8001"
echo "📖 API docs available at: http://localhost:8001/docs"
