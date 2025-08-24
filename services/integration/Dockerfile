# Multi-stage production Docker build for Anumate Integration Service
FROM python:3.11-slim-bullseye AS builder

LABEL maintainer="Anumate <info@anumate.com>"
LABEL description="Production-grade service integration patterns for Anumate platform"

# Build arguments
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=latest

# Metadata
LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.url="https://anumate.com" \
      org.opencontainers.image.source="https://github.com/anumate/platform" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.vendor="Anumate" \
      org.opencontainers.image.title="Anumate Integration Service" \
      org.opencontainers.image.description="Service integration patterns and infrastructure"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up Python environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create app directory
WORKDIR /app

# Copy requirements and install dependencies
COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e .[dev] && \
    pip install gunicorn[gevent]

# Production stage
FROM python:3.11-slim-bullseye AS production

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    dumb-init \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -g 1000 anumate && \
    useradd -r -u 1000 -g anumate anumate

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/anumate/.local/bin:$PATH" \
    PYTHONPATH="/app/src"

# Create app directory and set ownership
WORKDIR /app
RUN chown -R anumate:anumate /app

# Switch to non-root user
USER anumate

# Copy Python dependencies from builder
COPY --from=builder --chown=anumate:anumate /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder --chown=anumate:anumate /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=anumate:anumate src/ ./src/
COPY --chown=anumate:anumate pyproject.toml ./

# Install the package
USER root
RUN pip install -e .
USER anumate

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1

# Expose ports
EXPOSE 8090 8080

# Set up proper signal handling and process management
ENTRYPOINT ["dumb-init", "--"]

# Default command (can be overridden)
CMD ["python", "-m", "uvicorn", "anumate_integration_service.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8090", \
     "--workers", "4", \
     "--log-level", "info"]
