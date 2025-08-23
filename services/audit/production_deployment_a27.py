"""
A.27 Audit Service Production Deployment Configuration
=====================================================

Production-ready deployment configurations for the Audit Service including
Docker, Kubernetes, monitoring, and infrastructure setup.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List


class AuditServiceDeployer:
    """Production deployment configuration generator for A.27 Audit Service."""
    
    def __init__(self, service_dir: Path):
        self.service_dir = service_dir
        self.deployment_dir = service_dir / "deployment"
        self.deployment_dir.mkdir(exist_ok=True)
        
    def generate_all_configs(self):
        """Generate all production deployment configurations."""
        print("🚀 Generating A.27 Audit Service production deployment configurations...")
        
        # Core service files
        self._generate_dockerfile()
        self._generate_docker_compose()
        self._generate_requirements()
        
        # Kubernetes configurations
        self._generate_kubernetes_configs()
        
        # Monitoring and observability
        self._generate_monitoring_configs()
        
        # Database configurations
        self._generate_database_configs()
        
        # Infrastructure scripts
        self._generate_infrastructure_scripts()
        
        print("✅ All A.27 Audit Service deployment configurations generated!")
        
    def _generate_dockerfile(self):
        """Generate production Dockerfile."""
        dockerfile_content = '''# A.27 Audit Service Production Dockerfile
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    libpq-dev \\
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \\
    libpq5 \\
    curl \\
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
RUN mkdir -p /app/exports /app/logs && \\
    chown -R audit:audit /app/exports /app/logs

# Switch to non-root user
USER audit

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD curl -f http://localhost:8007/health || exit 1

# Expose port
EXPOSE 8007

# Start application
CMD ["uvicorn", "src.anumate_audit_service.app:app", "--host", "0.0.0.0", "--port", "8007", "--workers", "4"]
'''
        
        dockerfile_path = self.service_dir / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)
        print(f"📝 Generated {dockerfile_path}")
        
    def _generate_docker_compose(self):
        """Generate Docker Compose configuration."""
        compose_config = {
            "version": "3.8",
            "services": {
                "audit-service": {
                    "build": {
                        "context": ".",
                        "dockerfile": "Dockerfile"
                    },
                    "ports": ["8007:8007"],
                    "environment": [
                        "DATABASE_URL=postgresql+asyncpg://audit:audit_pass@audit-db:5432/audit_db",
                        "REDIS_URL=redis://audit-redis:6379/0",
                        "LOG_LEVEL=INFO",
                        "ENVIRONMENT=production",
                        "EXPORT_DIRECTORY=/app/exports",
                        "RETENTION_CHECK_INTERVAL=3600"
                    ],
                    "volumes": [
                        "audit_exports:/app/exports",
                        "audit_logs:/app/logs"
                    ],
                    "depends_on": [
                        "audit-db",
                        "audit-redis"
                    ],
                    "networks": ["audit-network"],
                    "restart": "unless-stopped",
                    "deploy": {
                        "resources": {
                            "limits": {
                                "memory": "1G",
                                "cpus": "0.5"
                            },
                            "reservations": {
                                "memory": "512M",
                                "cpus": "0.25"
                            }
                        }
                    }
                },
                "audit-db": {
                    "image": "postgres:15",
                    "environment": [
                        "POSTGRES_DB=audit_db",
                        "POSTGRES_USER=audit",
                        "POSTGRES_PASSWORD=audit_pass"
                    ],
                    "volumes": [
                        "audit_db_data:/var/lib/postgresql/data",
                        "./database/init.sql:/docker-entrypoint-initdb.d/init.sql"
                    ],
                    "ports": ["5432:5432"],
                    "networks": ["audit-network"],
                    "restart": "unless-stopped",
                    "command": [
                        "postgres",
                        "-c", "max_connections=200",
                        "-c", "shared_buffers=256MB",
                        "-c", "effective_cache_size=1GB",
                        "-c", "work_mem=4MB",
                        "-c", "maintenance_work_mem=64MB"
                    ]
                },
                "audit-redis": {
                    "image": "redis:7-alpine",
                    "ports": ["6379:6379"],
                    "volumes": [
                        "audit_redis_data:/data",
                        "./redis/redis.conf:/usr/local/etc/redis/redis.conf"
                    ],
                    "networks": ["audit-network"],
                    "restart": "unless-stopped",
                    "command": ["redis-server", "/usr/local/etc/redis/redis.conf"]
                },
                "audit-worker": {
                    "build": {
                        "context": ".",
                        "dockerfile": "Dockerfile"
                    },
                    "environment": [
                        "DATABASE_URL=postgresql+asyncpg://audit:audit_pass@audit-db:5432/audit_db",
                        "REDIS_URL=redis://audit-redis:6379/0",
                        "LOG_LEVEL=INFO",
                        "ENVIRONMENT=production",
                        "EXPORT_DIRECTORY=/app/exports"
                    ],
                    "volumes": [
                        "audit_exports:/app/exports",
                        "audit_logs:/app/logs"
                    ],
                    "depends_on": [
                        "audit-db",
                        "audit-redis"
                    ],
                    "networks": ["audit-network"],
                    "restart": "unless-stopped",
                    "command": ["python", "-m", "src.anumate_audit_service.worker"]
                }
            },
            "volumes": {
                "audit_db_data": {},
                "audit_redis_data": {},
                "audit_exports": {},
                "audit_logs": {}
            },
            "networks": {
                "audit-network": {
                    "driver": "bridge"
                }
            }
        }
        
        compose_path = self.service_dir / "docker-compose.production.yml"
        with open(compose_path, 'w') as f:
            yaml.dump(compose_config, f, default_flow_style=False, sort_keys=False)
        print(f"📝 Generated {compose_path}")
        
    def _generate_requirements(self):
        """Generate production requirements.txt."""
        requirements = [
            "fastapi[all]==0.104.1",
            "uvicorn[standard]==0.24.0",
            "sqlalchemy[asyncio]==2.0.23",
            "asyncpg==0.29.0",
            "alembic==1.12.1",
            "redis[hiredis]==5.0.1",
            "pydantic==2.5.0",
            "pydantic-settings==2.1.0",
            "python-multipart==0.0.6",
            "aiofiles==23.2.1",
            "python-json-logger==2.0.7",
            "structlog==23.2.0",
            "prometheus-client==0.19.0",
            "opentelemetry-api==1.21.0",
            "opentelemetry-sdk==1.21.0",
            "opentelemetry-instrumentation-fastapi==0.42b0",
            "opentelemetry-instrumentation-sqlalchemy==0.42b0",
            "opentelemetry-instrumentation-redis==0.42b0",
            "cryptography==41.0.7",
            "python-jose[cryptography]==3.3.0",
            "passlib[bcrypt]==1.7.4",
            "celery==5.3.4",
            "kombu==5.3.4"
        ]
        
        requirements_path = self.service_dir / "requirements.txt"
        requirements_path.write_text("\\n".join(requirements) + "\\n")
        print(f"📝 Generated {requirements_path}")
        
    def _generate_kubernetes_configs(self):
        """Generate Kubernetes deployment configurations."""
        k8s_dir = self.deployment_dir / "kubernetes"
        k8s_dir.mkdir(exist_ok=True)
        
        # Namespace
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "anumate-audit",
                "labels": {
                    "name": "anumate-audit",
                    "app.kubernetes.io/name": "anumate-audit",
                    "app.kubernetes.io/part-of": "anumate-platform"
                }
            }
        }
        
        # ConfigMap
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "audit-service-config",
                "namespace": "anumate-audit"
            },
            "data": {
                "LOG_LEVEL": "INFO",
                "ENVIRONMENT": "production",
                "EXPORT_DIRECTORY": "/app/exports",
                "RETENTION_CHECK_INTERVAL": "3600",
                "MAX_EXPORT_SIZE_MB": "1000",
                "DEFAULT_RETENTION_DAYS": "2555"  # 7 years
            }
        }
        
        # Secret
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "audit-service-secrets",
                "namespace": "anumate-audit"
            },
            "type": "Opaque",
            "data": {
                # Base64 encoded values (these should be set during deployment)
                "DATABASE_URL": "cG9zdGdyZXNxbCthc3luY3BnOi8vYXVkaXQ6YXVkaXRfcGFzc0BhdWRpdC1kYjo1NDMyL2F1ZGl0X2Ri",
                "REDIS_URL": "cmVkaXM6Ly9hdWRpdC1yZWRpczozNjM5LzA=",
                "JWT_SECRET": "Y2hhbmdlLW1lLWluLXByb2R1Y3Rpb24="
            }
        }
        
        # Deployment
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "audit-service",
                "namespace": "anumate-audit",
                "labels": {
                    "app": "audit-service",
                    "version": "v1.0.0"
                }
            },
            "spec": {
                "replicas": 3,
                "selector": {
                    "matchLabels": {
                        "app": "audit-service"
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "audit-service",
                            "version": "v1.0.0"
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "audit-service",
                                "image": "anumate/audit-service:1.0.0",
                                "imagePullPolicy": "IfNotPresent",
                                "ports": [
                                    {
                                        "containerPort": 8007,
                                        "name": "http"
                                    }
                                ],
                                "envFrom": [
                                    {
                                        "configMapRef": {
                                            "name": "audit-service-config"
                                        }
                                    },
                                    {
                                        "secretRef": {
                                            "name": "audit-service-secrets"
                                        }
                                    }
                                ],
                                "resources": {
                                    "requests": {
                                        "memory": "512Mi",
                                        "cpu": "250m"
                                    },
                                    "limits": {
                                        "memory": "1Gi",
                                        "cpu": "500m"
                                    }
                                },
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": "/health",
                                        "port": 8007
                                    },
                                    "initialDelaySeconds": 30,
                                    "periodSeconds": 10,
                                    "timeoutSeconds": 5
                                },
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": "/health",
                                        "port": 8007
                                    },
                                    "initialDelaySeconds": 10,
                                    "periodSeconds": 5,
                                    "timeoutSeconds": 3
                                },
                                "volumeMounts": [
                                    {
                                        "name": "audit-exports",
                                        "mountPath": "/app/exports"
                                    },
                                    {
                                        "name": "audit-logs",
                                        "mountPath": "/app/logs"
                                    }
                                ]
                            }
                        ],
                        "volumes": [
                            {
                                "name": "audit-exports",
                                "persistentVolumeClaim": {
                                    "claimName": "audit-exports-pvc"
                                }
                            },
                            {
                                "name": "audit-logs",
                                "emptyDir": {}
                            }
                        ]
                    }
                },
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": 1,
                        "maxUnavailable": 0
                    }
                }
            }
        }
        
        # Service
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "audit-service",
                "namespace": "anumate-audit",
                "labels": {
                    "app": "audit-service"
                }
            },
            "spec": {
                "selector": {
                    "app": "audit-service"
                },
                "ports": [
                    {
                        "port": 80,
                        "targetPort": 8007,
                        "protocol": "TCP",
                        "name": "http"
                    }
                ],
                "type": "ClusterIP"
            }
        }
        
        # PVC for exports
        pvc = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "audit-exports-pvc",
                "namespace": "anumate-audit"
            },
            "spec": {
                "accessModes": ["ReadWriteMany"],
                "resources": {
                    "requests": {
                        "storage": "100Gi"
                    }
                },
                "storageClassName": "fast-ssd"
            }
        }
        
        # Write all Kubernetes configs
        configs = {
            "01-namespace.yaml": namespace,
            "02-configmap.yaml": configmap,
            "03-secret.yaml": secret,
            "04-pvc.yaml": pvc,
            "05-deployment.yaml": deployment,
            "06-service.yaml": service
        }
        
        for filename, config in configs.items():
            config_path = k8s_dir / filename
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"📝 Generated {config_path}")
            
    def _generate_monitoring_configs(self):
        """Generate monitoring and observability configurations."""
        monitoring_dir = self.deployment_dir / "monitoring"
        monitoring_dir.mkdir(exist_ok=True)
        
        # Prometheus configuration
        prometheus_config = {
            "global": {
                "scrape_interval": "15s",
                "evaluation_interval": "15s"
            },
            "scrape_configs": [
                {
                    "job_name": "audit-service",
                    "static_configs": [
                        {
                            "targets": ["audit-service:8007"]
                        }
                    ],
                    "metrics_path": "/metrics",
                    "scrape_interval": "10s"
                }
            ]
        }
        
        prometheus_path = monitoring_dir / "prometheus.yml"
        with open(prometheus_path, 'w') as f:
            yaml.dump(prometheus_config, f, default_flow_style=False)
        print(f"📝 Generated {prometheus_path}")
        
        # Grafana dashboard
        grafana_dashboard = {
            "dashboard": {
                "id": None,
                "title": "A.27 Audit Service Dashboard",
                "tags": ["anumate", "audit"],
                "timezone": "browser",
                "panels": [
                    {
                        "id": 1,
                        "title": "Request Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(http_requests_total{service=\"audit-service\"}[5m])",
                                "legendFormat": "{{method}} {{endpoint}}"
                            }
                        ]
                    },
                    {
                        "id": 2,
                        "title": "Response Time",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service=\"audit-service\"}[5m]))",
                                "legendFormat": "95th percentile"
                            }
                        ]
                    },
                    {
                        "id": 3,
                        "title": "Audit Events Created",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "increase(audit_events_created_total[1h])",
                                "legendFormat": "Events/hour"
                            }
                        ]
                    },
                    {
                        "id": 4,
                        "title": "Database Connection Pool",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "db_connection_pool_active{service=\"audit-service\"}",
                                "legendFormat": "Active connections"
                            }
                        ]
                    }
                ],
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "refresh": "30s"
            }
        }
        
        grafana_path = monitoring_dir / "audit-service-dashboard.json"
        with open(grafana_path, 'w') as f:
            json.dump(grafana_dashboard, f, indent=2)
        print(f"📝 Generated {grafana_path}")
        
    def _generate_database_configs(self):
        """Generate database configuration files."""
        db_dir = self.deployment_dir / "database"
        db_dir.mkdir(exist_ok=True)
        
        # Database initialization script
        init_sql = '''-- A.27 Audit Service Database Initialization
-- PostgreSQL initialization script for production deployment

-- Create audit database (if using superuser)
-- CREATE DATABASE audit_db OWNER audit;

-- Connect to the audit database
\\c audit_db;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create audit user with limited privileges (if not exists)
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'audit') THEN
      CREATE ROLE audit LOGIN PASSWORD 'audit_pass';
   END IF;
END
$$;

-- Grant necessary permissions
GRANT CREATE, CONNECT ON DATABASE audit_db TO audit;
GRANT USAGE, CREATE ON SCHEMA public TO audit;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO audit;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO audit;

-- Create read-only user for reporting
CREATE ROLE audit_reader LOGIN PASSWORD 'reader_pass';
GRANT CONNECT ON DATABASE audit_db TO audit_reader;
GRANT USAGE ON SCHEMA public TO audit_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO audit_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO audit_reader;

-- Performance optimizations
-- Increase work_mem for better query performance
ALTER DATABASE audit_db SET work_mem = '64MB';

-- Configure for audit logging workload
ALTER DATABASE audit_db SET random_page_cost = 1.1;
ALTER DATABASE audit_db SET effective_cache_size = '2GB';

-- Create tablespaces for better I/O distribution (optional)
-- CREATE TABLESPACE audit_events LOCATION '/var/lib/postgresql/tablespaces/audit_events';
-- CREATE TABLESPACE audit_indexes LOCATION '/var/lib/postgresql/tablespaces/audit_indexes';

COMMIT;
'''
        
        init_sql_path = db_dir / "init.sql"
        init_sql_path.write_text(init_sql)
        print(f"📝 Generated {init_sql_path}")
        
        # PostgreSQL configuration
        postgres_conf = '''# A.27 Audit Service PostgreSQL Configuration
# Optimized for audit logging workload

# Memory settings
shared_buffers = 256MB
effective_cache_size = 2GB
work_mem = 64MB
maintenance_work_mem = 256MB

# Checkpoint settings
checkpoint_completion_target = 0.9
checkpoint_timeout = 15min
max_wal_size = 2GB
min_wal_size = 512MB

# Connection settings
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

# Logging settings
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_min_duration_statement = 1000
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on

# Performance monitoring
track_activities = on
track_counts = on
track_io_timing = on
track_functions = all

# Audit settings
log_statement = 'ddl'
log_min_messages = warning
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '

# Replication (for HA setup)
wal_level = replica
max_wal_senders = 3
wal_keep_segments = 64
'''
        
        postgres_conf_path = db_dir / "postgresql.conf"
        postgres_conf_path.write_text(postgres_conf)
        print(f"📝 Generated {postgres_conf_path}")
        
    def _generate_infrastructure_scripts(self):
        """Generate infrastructure deployment scripts."""
        scripts_dir = self.deployment_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        
        # Deployment script
        deploy_script = '''#!/bin/bash
# A.27 Audit Service Deployment Script

set -e

echo "🚀 Deploying A.27 Audit Service to production..."

# Configuration
NAMESPACE="anumate-audit"
IMAGE_TAG=${IMAGE_TAG:-"1.0.0"}
DOCKER_REGISTRY=${DOCKER_REGISTRY:-"your-registry.com"}

# Functions
check_dependencies() {
    echo "🔍 Checking dependencies..."
    
    if ! command -v kubectl &> /dev/null; then
        echo "❌ kubectl is not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo "❌ docker is not installed"
        exit 1
    fi
    
    echo "✅ Dependencies check passed"
}

build_and_push_image() {
    echo "🏗️ Building and pushing Docker image..."
    
    docker build -t ${DOCKER_REGISTRY}/anumate/audit-service:${IMAGE_TAG} .
    docker push ${DOCKER_REGISTRY}/anumate/audit-service:${IMAGE_TAG}
    
    echo "✅ Docker image built and pushed"
}

deploy_to_kubernetes() {
    echo "☸️ Deploying to Kubernetes..."
    
    # Apply Kubernetes configurations
    kubectl apply -f deployment/kubernetes/01-namespace.yaml
    kubectl apply -f deployment/kubernetes/02-configmap.yaml
    kubectl apply -f deployment/kubernetes/03-secret.yaml
    kubectl apply -f deployment/kubernetes/04-pvc.yaml
    kubectl apply -f deployment/kubernetes/05-deployment.yaml
    kubectl apply -f deployment/kubernetes/06-service.yaml
    
    # Wait for deployment to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/audit-service -n ${NAMESPACE}
    
    echo "✅ Kubernetes deployment completed"
}

run_database_migrations() {
    echo "🗃️ Running database migrations..."
    
    # Get a pod to run migrations
    POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app=audit-service -o jsonpath="{.items[0].metadata.name}")
    
    if [ ! -z "$POD_NAME" ]; then
        kubectl exec -n ${NAMESPACE} ${POD_NAME} -- alembic upgrade head
        echo "✅ Database migrations completed"
    else
        echo "⚠️ No pods found to run migrations"
    fi
}

verify_deployment() {
    echo "🔍 Verifying deployment..."
    
    # Check service status
    kubectl get deployments -n ${NAMESPACE}
    kubectl get services -n ${NAMESPACE}
    kubectl get pods -n ${NAMESPACE}
    
    # Test health endpoint
    echo "Testing health endpoint..."
    SERVICE_IP=$(kubectl get service audit-service -n ${NAMESPACE} -o jsonpath="{.spec.clusterIP}")
    
    # Port forward for testing (in background)
    kubectl port-forward service/audit-service -n ${NAMESPACE} 8007:80 &
    PORT_FORWARD_PID=$!
    sleep 5
    
    if curl -f http://localhost:8007/health; then
        echo "✅ Health check passed"
    else
        echo "❌ Health check failed"
        kill $PORT_FORWARD_PID
        exit 1
    fi
    
    kill $PORT_FORWARD_PID
}

# Main execution
main() {
    echo "Starting A.27 Audit Service deployment..."
    
    check_dependencies
    build_and_push_image
    deploy_to_kubernetes
    run_database_migrations
    verify_deployment
    
    echo "🎉 A.27 Audit Service deployment completed successfully!"
    echo "Service is available at: audit-service.anumate-audit.svc.cluster.local"
}

# Execute main function
main "$@"
'''
        
        deploy_script_path = scripts_dir / "deploy.sh"
        deploy_script_path.write_text(deploy_script)
        deploy_script_path.chmod(0o755)
        print(f"📝 Generated {deploy_script_path}")
        
        # Environment setup script
        env_script = '''#!/bin/bash
# A.27 Audit Service Environment Setup

set -e

echo "🛠️ Setting up A.27 Audit Service environment..."

# Create necessary directories
mkdir -p /app/exports
mkdir -p /app/logs
mkdir -p /app/backups

# Set proper permissions
chown -R audit:audit /app/exports
chown -R audit:audit /app/logs
chown -R audit:audit /app/backups

# Create systemd service (for non-containerized deployments)
if command -v systemctl &> /dev/null; then
    cat > /etc/systemd/system/anumate-audit.service << EOF
[Unit]
Description=Anumate A.27 Audit Service
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=exec
User=audit
Group=audit
WorkingDirectory=/app
Environment=PYTHONPATH=/app
ExecStart=/usr/local/bin/uvicorn src.anumate_audit_service.app:app --host 0.0.0.0 --port 8007 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable anumate-audit.service
    echo "✅ Systemd service created and enabled"
fi

# Create log rotation configuration
cat > /etc/logrotate.d/anumate-audit << EOF
/app/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 audit audit
    postrotate
        systemctl reload anumate-audit || true
    endscript
}
EOF

echo "✅ Log rotation configured"

# Setup backup script
cat > /app/scripts/backup.sh << EOF
#!/bin/bash
# A.27 Audit Service Backup Script

BACKUP_DIR="/app/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="audit_db"

# Database backup
pg_dump -h localhost -U audit -d \${DB_NAME} | gzip > \${BACKUP_DIR}/audit_db_\${DATE}.sql.gz

# Export files backup
tar czf \${BACKUP_DIR}/exports_\${DATE}.tar.gz /app/exports

# Cleanup old backups (keep 30 days)
find \${BACKUP_DIR} -name "*.gz" -mtime +30 -delete

echo "Backup completed: \${DATE}"
EOF

chmod +x /app/scripts/backup.sh
echo "✅ Backup script created"

# Setup monitoring
if command -v crontab &> /dev/null; then
    # Add backup cron job
    (crontab -l 2>/dev/null; echo "0 2 * * * /app/scripts/backup.sh >> /app/logs/backup.log 2>&1") | crontab -
    echo "✅ Backup cron job added"
fi

echo "🎉 A.27 Audit Service environment setup completed!"
'''
        
        env_script_path = scripts_dir / "setup_environment.sh"
        env_script_path.write_text(env_script)
        env_script_path.chmod(0o755)
        print(f"📝 Generated {env_script_path}")


def main():
    """Generate all A.27 Audit Service production deployment configurations."""
    import sys
    
    # Get service directory
    if len(sys.argv) > 1:
        service_dir = Path(sys.argv[1])
    else:
        service_dir = Path(__file__).parent
        
    if not service_dir.exists():
        print(f"❌ Service directory {service_dir} does not exist")
        sys.exit(1)
        
    # Generate configurations
    deployer = AuditServiceDeployer(service_dir)
    deployer.generate_all_configs()
    
    print()
    print("📋 Next Steps:")
    print("1. Review and customize the generated configurations")
    print("2. Update secrets and environment variables for your environment")
    print("3. Build and push Docker images")
    print("4. Deploy using: ./deployment/scripts/deploy.sh")
    print("5. Run integration tests: python integration_test_a27.py")


if __name__ == "__main__":
    main()
