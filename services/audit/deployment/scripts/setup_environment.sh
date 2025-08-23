#!/bin/bash
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
