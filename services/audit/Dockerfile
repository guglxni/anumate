# A.27 Audit Service Production Dockerfile
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash audit

# Create app directory and set ownership
WORKDIR /app
RUN chown -R audit:audit /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=audit:audit src/ ./src/
COPY --chown=audit:audit alembic/ ./alembic/
COPY --chown=audit:audit alembic.ini .
COPY --chown=audit:audit logging.yaml .

# Create required directories
RUN mkdir -p /app/exports /app/logs && \
    chown -R audit:audit /app/exports /app/logs

# Switch to non-root user
USER audit

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

# Expose port
EXPOSE 8007

# Start application
CMD ["uvicorn", "src.anumate_audit_service.app:app", "--host", "0.0.0.0", "--port", "8007", "--workers", "4"]
