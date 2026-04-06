#!/bin/bash

BACKUP_DIR="/home/ubuntu/backups"
TARGET_DIR="/home/ubuntu/jarvis-field"
DATE=$(date +%Y%m%d_%H%M)

mkdir -p $BACKUP_DIR

tar -czf $BACKUP_DIR/jarvis_backup_$DATE.tar.gz $TARGET_DIR

# 오래된 백업 삭제 (최근 5개만 유지)
ls -tp $BACKUP_DIR | grep '.tar.gz' | tail -n +6 | xargs -I {} rm -- $BACKUP_DIR/{}

echo "Backup complete: $DATE"
