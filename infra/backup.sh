#!/bin/sh
# Nightly Ace database backup — full pg_dump, gzipped, 14-day rotation.
# Restore: gunzip -c <file> | docker exec -i ace-db psql -U ace -d ace
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)/backups"
mkdir -p "$DIR"
STAMP=$(date +%Y%m%d-%H%M)
docker exec ace-db pg_dump -U ace -d ace --clean --if-exists | gzip > "$DIR/ace-$STAMP.sql.gz"
# verify the dump is non-trivial before trusting it
SIZE=$(stat -c%s "$DIR/ace-$STAMP.sql.gz")
if [ "$SIZE" -lt 10000 ]; then
  echo "backup suspiciously small ($SIZE bytes)" >&2
  exit 1
fi
ls -1t "$DIR"/ace-*.sql.gz | tail -n +15 | xargs -r rm --
echo "backup ok: ace-$STAMP.sql.gz ($SIZE bytes), $(ls "$DIR" | wc -l) kept"

# off-disk copy: whenever the SanDisk is attached, mirror the backup set to it
SSD_ROOT="${ACE_SSD_MOUNT:-/media/$USER/Extreme SSD}"
SSD="$SSD_ROOT/Ace-backups"
if [ -d "$SSD_ROOT" ]; then
  mkdir -p "$SSD" && rsync -a --delete "$DIR/" "$SSD/" \
    && echo "ssd mirror ok" || echo "ssd mirror failed (non-fatal)" >&2
fi
