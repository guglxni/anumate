#!/bin/bash
# Initialize NATS JetStream streams for Anumate event bus

set -e

# Configuration
NATS_URL=${NATS_URL:-"nats://anumate_app:app_password@localhost:4222"}

echo "Initializing NATS JetStream streams for Anumate..."

# Check if nats CLI is available
if ! command -v nats &> /dev/null; then
    echo "NATS CLI not found. Installing..."
    # Install NATS CLI (adjust for your OS)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install nats-io/nats-tools/nats
        else
            echo "Please install NATS CLI manually: https://github.com/nats-io/natscli"
            exit 1
        fi
    else
        echo "Please install NATS CLI manually: https://github.com/nats-io/natscli"
        exit 1
    fi
fi

# Wait for NATS to be ready
echo "Waiting for NATS JetStream to be ready..."
until nats --server="$NATS_URL" stream ls &> /dev/null; do
    echo "NATS JetStream is unavailable - sleeping"
    sleep 2
done

# Create streams for different event types
echo "Creating event streams..."

# Capsule events stream
nats --server="$NATS_URL" stream add CAPSULE_EVENTS \
    --subjects="events.capsule.*" \
    --storage=file \
    --retention=limits \
    --max-msgs=1000000 \
    --max-bytes=1GB \
    --max-age=30d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=2m || true

# Plan events stream
nats --server="$NATS_URL" stream add PLAN_EVENTS \
    --subjects="events.plan.*" \
    --storage=file \
    --retention=limits \
    --max-msgs=1000000 \
    --max-bytes=1GB \
    --max-age=30d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=2m || true

# Execution events stream
nats --server="$NATS_URL" stream add EXECUTION_EVENTS \
    --subjects="events.execution.*" \
    --storage=file \
    --retention=limits \
    --max-msgs=1000000 \
    --max-bytes=1GB \
    --max-age=90d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=2m || true

# Approval events stream
nats --server="$NATS_URL" stream add APPROVAL_EVENTS \
    --subjects="events.approval.*" \
    --storage=file \
    --retention=limits \
    --max-msgs=1000000 \
    --max-bytes=1GB \
    --max-age=365d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=2m || true

# Audit events stream (longer retention)
nats --server="$NATS_URL" stream add AUDIT_EVENTS \
    --subjects="events.audit.*" \
    --storage=file \
    --retention=limits \
    --max-msgs=10000000 \
    --max-bytes=10GB \
    --max-age=2555d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=5m || true

# System events stream
nats --server="$NATS_URL" stream add SYSTEM_EVENTS \
    --subjects="events.system.*" \
    --storage=file \
    --retention=limits \
    --max-msgs=1000000 \
    --max-bytes=1GB \
    --max-age=30d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=2m || true

# Webhook delivery stream
nats --server="$NATS_URL" stream add WEBHOOK_DELIVERY \
    --subjects="webhooks.*" \
    --storage=file \
    --retention=workqueue \
    --max-msgs=100000 \
    --max-bytes=100MB \
    --max-age=7d \
    --max-msg-size=1MB \
    --discard=old \
    --dupe-window=1m || true

echo "Creating consumers for event processing..."

# Create durable consumers for event processing
nats --server="$NATS_URL" consumer add CAPSULE_EVENTS capsule-processor \
    --filter="events.capsule.*" \
    --ack=explicit \
    --pull \
    --deliver=all \
    --max-deliver=3 \
    --wait=30s || true

nats --server="$NATS_URL" consumer add PLAN_EVENTS plan-processor \
    --filter="events.plan.*" \
    --ack=explicit \
    --pull \
    --deliver=all \
    --max-deliver=3 \
    --wait=30s || true

nats --server="$NATS_URL" consumer add EXECUTION_EVENTS execution-processor \
    --filter="events.execution.*" \
    --ack=explicit \
    --pull \
    --deliver=all \
    --max-deliver=3 \
    --wait=30s || true

nats --server="$NATS_URL" consumer add APPROVAL_EVENTS approval-processor \
    --filter="events.approval.*" \
    --ack=explicit \
    --pull \
    --deliver=all \
    --max-deliver=3 \
    --wait=30s || true

nats --server="$NATS_URL" consumer add AUDIT_EVENTS audit-processor \
    --filter="events.audit.*" \
    --ack=explicit \
    --pull \
    --deliver=all \
    --max-deliver=5 \
    --wait=60s || true

nats --server="$NATS_URL" consumer add WEBHOOK_DELIVERY webhook-processor \
    --filter="webhooks.*" \
    --ack=explicit \
    --pull \
    --deliver=all \
    --max-deliver=5 \
    --wait=30s || true

# List created streams
echo "Created streams:"
nats --server="$NATS_URL" stream ls

echo "NATS JetStream initialization complete!"