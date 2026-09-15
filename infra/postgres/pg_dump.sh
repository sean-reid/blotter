#!/bin/bash
DUMP_DIR="/workspace/postgres-backup"
mkdir -p "$DUMP_DIR"
rm -f "$DUMP_DIR/blotter.dump.new"
su postgres -c "pg_dump -Fc -Z 9 blotter" > "$DUMP_DIR/blotter.dump.new" \
  && mv "$DUMP_DIR/blotter.dump.new" "$DUMP_DIR/blotter.dump"

# pg_dump reads the entire database into page cache, inflating the cgroup
# working set by ~1.2 GiB. Drop clean page cache so the memory alert
# doesn't fire on reclaimable pages.
sync
echo 1 > /proc/sys/vm/drop_caches 2>/dev/null
