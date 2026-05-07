#!/bin/bash
DUMP_DIR="/workspace/postgres-backup"
mkdir -p "$DUMP_DIR"
su postgres -c "pg_dump -Fc blotter" > "$DUMP_DIR/blotter.dump.new" \
  && mv "$DUMP_DIR/blotter.dump.new" "$DUMP_DIR/blotter.dump"
