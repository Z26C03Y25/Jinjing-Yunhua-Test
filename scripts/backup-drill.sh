#!/bin/sh
# Stop writers for a consistent full evidence backup, then restore into tmpfs.
set -eu
umask 077
mkdir -p .runtime-backups .runtime-reports
directory=$(cd .runtime-backups && pwd)
archive="evidence-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
restart() { docker compose start backend >/dev/null; }
trap restart EXIT INT TERM
docker compose stop backend
docker compose run --rm --no-deps --user 0:0 -v "$directory:/backup" backend \
    python3 /app/maintenance.py backup --archive "/backup/$archive"
docker compose start backend
trap - EXIT INT TERM
# This restoration cannot touch the live volume: target is independent tmpfs.
docker compose run --rm --no-deps --user 0:0 -v "$directory:/backup:ro" backend \
    python3 /app/maintenance.py restore --state /tmp/restore --archive "/backup/$archive" \
    > .runtime-reports/backup-drill.json
cat .runtime-reports/backup-drill.json
echo "Backup verified: $directory/$archive"
echo 'Keep an encrypted off-server copy. Backups contain sensitive PCAP and evidence, but exclude .env.'
