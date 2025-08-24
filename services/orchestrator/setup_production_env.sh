#!/bin/bash
# Production Environment Setup for Orchestrator Service
# WeMakeDevs AgentHack 2025 - Production Grade MVP

set -e

echo "🚀 Setting up production environment for Orchestrator Service..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to prompt for required environment variables
prompt_env_var() {
    local var_name=$1
    local description=$2
    local example=$3
    local current_value=$(printenv "$var_name" || echo "")
    
    echo -e "${BLUE}Setting $var_name${NC}"
    echo -e "Description: $description"
    echo -e "Example: $example"
    
    if [ -n "$current_value" ]; then
        echo -e "Current value: ${GREEN}${current_value:0:20}...${NC}"
        read -p "Keep current value? (y/n): " keep
        if [[ $keep =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi
    
    read -p "Enter $var_name: " value
    if [ -z "$value" ]; then
        echo -e "${RED}❌ $var_name is required for production deployment${NC}"
        exit 1
    fi
    
    # Add to shell profile
    echo "export $var_name=\"$value\"" >> ~/.zshrc
    export "$var_name"="$value"
    
    echo -e "${GREEN}✅ $var_name configured${NC}"
    echo ""
}

# Check if running in production mode
echo "🔍 Checking deployment environment..."

if [ "${NODE_ENV:-}" != "production" ] && [ "${ANUMATE_ENV:-}" != "production" ]; then
    echo -e "${YELLOW}⚠️  Production environment variables not detected${NC}"
    echo "This script sets up production-grade configuration."
    read -p "Continue with production setup? (y/n): " continue
    if [[ ! $continue =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

echo -e "${GREEN}📋 Production Environment Configuration${NC}"
echo "================================================"

# Required Portia Configuration
echo -e "${BLUE}🔑 Portia SDK Configuration${NC}"
echo "Get your credentials from: https://app.portia.ai/settings"
echo ""

prompt_env_var "PORTIA_API_KEY" \
    "Portia API key for plan execution" \
    "pk_live_abcd1234..."

prompt_env_var "PORTIA_WORKSPACE" \
    "Portia workspace UUID" \
    "12345678-1234-1234-1234-123456789012"

# Optional Portia Configuration
echo -e "${BLUE}🌐 Optional Portia Configuration${NC}"

# PORTIA_BASE_URL (optional)
current_base_url=$(printenv "PORTIA_BASE_URL" || echo "")
if [ -z "$current_base_url" ]; then
    read -p "Custom Portia Base URL (press Enter for default): " base_url
    if [ -n "$base_url" ]; then
        echo "export PORTIA_BASE_URL=\"$base_url\"" >> ~/.zshrc
        export PORTIA_BASE_URL="$base_url"
        echo -e "${GREEN}✅ PORTIA_BASE_URL configured${NC}"
    else
        echo "Using default Portia API endpoint"
    fi
else
    echo -e "PORTIA_BASE_URL already set: ${GREEN}$current_base_url${NC}"
fi

# Database Configuration
echo ""
echo -e "${BLUE}🗄️  Database Configuration${NC}"

# Check for PostgreSQL configuration
if [ -z "${DATABASE_URL:-}" ] && [ -z "${POSTGRES_HOST:-}" ]; then
    echo -e "${YELLOW}⚠️  No database configuration found${NC}"
    echo "Orchestrator service requires database for state management."
    
    read -p "Configure PostgreSQL? (y/n): " config_db
    if [[ $config_db =~ ^[Yy]$ ]]; then
        prompt_env_var "POSTGRES_HOST" \
            "PostgreSQL host" \
            "localhost or your-db-host.com"
        
        prompt_env_var "POSTGRES_PORT" \
            "PostgreSQL port" \
            "5432"
        
        prompt_env_var "POSTGRES_DB" \
            "PostgreSQL database name" \
            "anumate"
        
        prompt_env_var "POSTGRES_USER" \
            "PostgreSQL username" \
            "anumate_admin"
        
        prompt_env_var "POSTGRES_PASSWORD" \
            "PostgreSQL password" \
            "your_secure_password"
    fi
else
    echo -e "${GREEN}✅ Database configuration found${NC}"
fi

# Redis Configuration (for caching and idempotency)
echo ""
echo -e "${BLUE}📦 Redis Configuration${NC}"

if [ -z "${REDIS_URL:-}" ] && [ -z "${REDIS_HOST:-}" ]; then
    echo -e "${YELLOW}⚠️  No Redis configuration found${NC}"
    echo "Redis is recommended for production caching and idempotency."
    
    read -p "Configure Redis? (y/n): " config_redis
    if [[ $config_redis =~ ^[Yy]$ ]]; then
        prompt_env_var "REDIS_HOST" \
            "Redis host" \
            "localhost or redis.your-domain.com"
        
        prompt_env_var "REDIS_PORT" \
            "Redis port" \
            "6379"
        
        read -p "Redis password (optional): " redis_password
        if [ -n "$redis_password" ]; then
            echo "export REDIS_PASSWORD=\"$redis_password\"" >> ~/.zshrc
            export REDIS_PASSWORD="$redis_password"
        fi
    fi
else
    echo -e "${GREEN}✅ Redis configuration found${NC}"
fi

# Service Configuration
echo ""
echo -e "${BLUE}⚙️  Service Configuration${NC}"

# Service port
current_port=$(printenv "ORCHESTRATOR_PORT" || echo "")
if [ -z "$current_port" ]; then
    read -p "Orchestrator service port (default 8080): " service_port
    service_port=${service_port:-8080}
    echo "export ORCHESTRATOR_PORT=\"$service_port\"" >> ~/.zshrc
    export ORCHESTRATOR_PORT="$service_port"
else
    echo -e "Service port: ${GREEN}$current_port${NC}"
fi

# Log level
current_log_level=$(printenv "LOG_LEVEL" || echo "")
if [ -z "$current_log_level" ]; then
    echo "Select log level for production:"
    echo "1) INFO (recommended)"
    echo "2) WARNING"
    echo "3) ERROR"
    echo "4) DEBUG (not recommended for production)"
    read -p "Choice (1-4, default 1): " log_choice
    
    case $log_choice in
        2) log_level="WARNING" ;;
        3) log_level="ERROR" ;;
        4) log_level="DEBUG" ;;
        *) log_level="INFO" ;;
    esac
    
    echo "export LOG_LEVEL=\"$log_level\"" >> ~/.zshrc
    export LOG_LEVEL="$log_level"
    echo -e "${GREEN}✅ Log level set to $log_level${NC}"
else
    echo -e "Log level: ${GREEN}$current_log_level${NC}"
fi

# Environment marker
echo "export ANUMATE_ENV=\"production\"" >> ~/.zshrc
export ANUMATE_ENV="production"

# Source the updated profile
echo ""
echo -e "${BLUE}🔄 Reloading shell configuration...${NC}"
source ~/.zshrc

# Validation
echo ""
echo -e "${BLUE}✅ Validating Configuration${NC}"
echo "================================"

# Test Portia SDK configuration
echo "Testing Portia SDK configuration..."

cd /Users/aaryanguglani/anumate

python3 -c "
import sys
sys.path.insert(0, 'services/orchestrator/src')

try:
    from portia_sdk_client import PortiaSDKClient, PortiaConfigurationError
    
    # Test client initialization
    try:
        client = PortiaSDKClient()
        print('✅ Portia SDK client initialized successfully')
        print(f'   API Key: {client.api_key[:20]}...')
        print(f'   Workspace: {client.workspace[:8]}...')
        print(f'   Base URL: {client.base_url}')
    except PortiaConfigurationError as e:
        print(f'❌ Configuration Error: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'❌ Initialization Error: {e}')
        sys.exit(1)
        
    print('🎉 Production configuration is valid!')
    
except ImportError as e:
    print(f'❌ Import Error: {e}')
    print('Make sure portia-sdk-python is installed: pip install portia-sdk-python')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Configuration validation passed${NC}"
else
    echo -e "${RED}❌ Configuration validation failed${NC}"
    echo "Please check the error messages above and fix any issues."
    exit 1
fi

# Summary
echo ""
echo -e "${GREEN}🎉 Production Environment Setup Complete!${NC}"
echo "=============================================="
echo -e "Environment: ${GREEN}PRODUCTION${NC}"
echo -e "Portia SDK: ${GREEN}Configured${NC}"
echo -e "Service Port: ${GREEN}${ORCHESTRATOR_PORT:-8080}${NC}"
echo -e "Log Level: ${GREEN}${LOG_LEVEL:-INFO}${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. Start the orchestrator service:"
echo "   cd services/orchestrator && python -m uvicorn src.main:app --host 0.0.0.0 --port ${ORCHESTRATOR_PORT:-8080}"
echo ""
echo "2. Test the service:"
echo "   curl http://localhost:${ORCHESTRATOR_PORT:-8080}/health"
echo ""
echo "3. Monitor logs for any issues"
echo ""
echo -e "${YELLOW}⚠️  Remember to:${NC}"
echo "- Keep API keys secure and rotate regularly"
echo "- Monitor Portia API usage and limits"
echo "- Set up proper error monitoring"
echo "- Back up configuration and secrets"
echo ""
echo -e "${GREEN}Happy AgentHack 2025! 🚀${NC}"
