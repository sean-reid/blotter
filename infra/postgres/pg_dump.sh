#!/bin/bash
DUMP_DIR="/workspace/postgres-backup"
mkdir -p "$DUMP_DIR"
rm -f "$DUMP_DIR/blotter.dump.new"
su postgres -c "pg_dump -Fc -Z 9 blotter" > "$DUMP_DIR/blotter.dump.new" \
  && mv "$DUMP_DIR/blotter.dump.new" "$DUMP_DIR/blotter.dump"
