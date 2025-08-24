# Capsule Registry Service Makefile

.PHONY: help test test-registry run run-registry clean lint install dev-install

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Test targets
test: test-registry  ## Run all tests

test-registry:  ## Run Capsule Registry tests (SQLite, no Docker)
	@echo "🧪 Running Capsule Registry tests..."
	@cd /Users/aaryanguglani/anumate && python -m pytest services/registry/tests -v --tb=short --disable-warnings

test-coverage:  ## Run tests with coverage report
	@echo "📊 Running tests with coverage..."
	@cd /Users/aaryanguglani/anumate && python -m pytest services/registry/tests --cov=services.registry --cov-report=term-missing

# Run targets
run: run-registry  ## Run the service

run-registry:  ## Run Capsule Registry service (development mode)
	@echo "🚀 Starting Capsule Registry service..."
	@cd /Users/aaryanguglani/anumate && python -m uvicorn services.registry.main:app --host 0.0.0.0 --port 8000 --reload

run-prod:  ## Run in production mode
	@echo "🚀 Starting Capsule Registry service (production)..."
	@cd /Users/aaryanguglani/anumate && python -m uvicorn services.registry.main:app --host 0.0.0.0 --port 8000 --workers 4

# Development targets
install:  ## Install dependencies
	@echo "📦 Installing dependencies..."
	@pip install -e .

dev-install:  ## Install development dependencies  
	@echo "🛠️ Installing development dependencies..."
	@pip install -e ".[dev]"

# Linting and validation
lint:  ## Run code linting
	@echo "🔍 Running linters..."
	@python -m ruff check services/registry/
	@python -m mypy services/registry/

validate-api:  ## Validate OpenAPI specification
	@echo "✅ Validating API specification..."
	@cd /Users/aaryanguglani/anumate && python -c "import yaml; yaml.safe_load(open('services/registry/api.yaml')); print('✅ API specification valid')"

validate-schema:  ## Validate using schemathesis
	@echo "🔍 Running schemathesis validation..."
	@cd /Users/aaryanguglani/anumate && schemathesis run services/registry/api.yaml --checks all --hypothesis-deadline=none

# Database targets
db-upgrade:  ## Run database migrations
	@echo "📈 Running database migrations..."
	@cd /Users/aaryanguglani/anumate/services/registry && alembic upgrade head

db-downgrade:  ## Rollback database migrations
	@echo "📉 Rolling back database migrations..."
	@cd /Users/aaryanguglani/anumate/services/registry && alembic downgrade -1

db-revision:  ## Create new database migration
	@echo "📝 Creating database migration..."
	@cd /Users/aaryanguglani/anumate/services/registry && alembic revision --autogenerate -m "$(MESSAGE)"

# Cleanup targets  
clean:  ## Clean build artifacts
	@echo "🧹 Cleaning build artifacts..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf .pytest_cache/
	@rm -rf .coverage
	@rm -rf htmlcov/
	@rm -rf dist/
	@rm -rf build/
	@rm -rf *.egg-info/

# Docker targets (optional)
docker-build:  ## Build Docker image
	@echo "🐳 Building Docker image..."
	@docker build -t anumate-registry:latest .

docker-run:  ## Run in Docker container
	@echo "🐳 Running Docker container..."
	@docker run -p 8000:8000 --env-file .env anumate-registry:latest
