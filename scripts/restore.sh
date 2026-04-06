#!/bin/bash

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: restore.sh <backup_file>"
  exit 1
fi

echo "Restoring from $BACKUP_FILE..."

cd /home/ubuntu
tar -xzf $BACKUP_FILE

sudo systemctl restart jarvis-8501.service
sudo systemctl restart jarvis-8501-api.service
sudo systemctl restart jarvis-8501-web.service

echo "Restore complete."
