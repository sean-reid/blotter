#!/bin/bash
DUMP_FILE="/workspace/postgres-backup/blotter.dump"
if [ ! -f "$DUMP_FILE" ]; then
  echo "No dump file found, starting fresh"
  exit 0
fi
echo "Restoring from $DUMP_FILE..."
su postgres -c "pg_restore -d blotter --clean --if-exists --no-owner $DUMP_FILE" 2>&1 | tail -5
echo "Restore complete"
