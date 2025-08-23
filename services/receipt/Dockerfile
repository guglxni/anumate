FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY . .

# Create non-root user
RUN groupadd -r receipt && useradd -r -g receipt receipt
RUN chown -R receipt:receipt /app
USER receipt

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/ || exit 1

# Start the service
CMD ["python", "-m", "uvicorn", "src.anumate_receipt_service.app_production:app", "--host", "0.0.0.0", "--port", "8001"]
