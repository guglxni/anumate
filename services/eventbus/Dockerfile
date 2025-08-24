# Multi-stage build for production deployment
FROM python:3.11-slim as builder

# Build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir build && \
    python -m build

# Production image
FROM python:3.11-slim as production

# Runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r anumate \
    && useradd -r -g anumate anumate

# Install the package
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm /tmp/*.whl

# Setup application
WORKDIR /app
USER anumate

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Default environment
ENV PYTHONPATH=/app
ENV NATS_URL=nats://localhost:4222
ENV REDIS_URL=redis://localhost:6379
ENV API_HOST=0.0.0.0
ENV API_PORT=8080

# Run the service
CMD ["uvicorn", "anumate_eventbus_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
