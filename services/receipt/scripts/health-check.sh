#!/bin/bash

echo "🏥 Receipt Service Health Check"
echo "=============================="

# Check service response
if curl -s -f http://localhost:8001/ > /dev/null; then
    echo "✅ Service is responding"
    
    # Get detailed health info
    curl -s http://localhost:8001/ | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'📋 Service: {data.get("service")}')
print(f'🔖 Version: {data.get("version")}')
print(f'⚡ Status: {data.get("status")}')
print(f'🔌 API Endpoints: {len(data.get("api_endpoints", []))}')
print(f'🎯 Features: {len(data.get("features", []))}')
"
    
    # Check database connection
    echo ""
    echo "🗄️  Database Connection Check:"
    if docker exec anumate-postgres pg_isready -U anumate_admin -d anumate > /dev/null 2>&1; then
        echo "✅ PostgreSQL is accessible"
    else
        echo "❌ PostgreSQL connection failed"
    fi
    
    # Check Redis connection  
    echo ""
    echo "🔴 Redis Connection Check:"
    if docker exec anumate-redis redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis is accessible"
    else
        echo "❌ Redis connection failed"
    fi
    
else
    echo "❌ Service is not responding"
    echo "Check logs with: docker-compose -f docker-compose.production.yml logs"
    exit 1
fi
