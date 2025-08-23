#!/bin/bash
set -e

echo "🏗️  Building Receipt Service for production..."

# Build Docker image
docker build -t anumate/receipt-service:v1.0.0 .

# Tag for registry
docker tag anumate/receipt-service:v1.0.0 registry.anumate.com/receipt-service:v1.0.0

echo "✅ Build completed successfully!"
echo "To push to registry: docker push registry.anumate.com/receipt-service:v1.0.0"
