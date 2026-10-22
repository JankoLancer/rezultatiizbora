#!/usr/bin/env bash
# Prepare map/ for serving from the repo (no Docker):
#   map/data.json.gz  ->  map/data.json
set -euo pipefail
cd "$(dirname "$0")/.."

for f in data.json odbori.json odbori.csv; do
  if [ -f "map/$f.gz" ] && [ ! -f "map/$f" ]; then
    gzip -dkf "map/$f.gz"
  fi
done
echo "OK: map/ spremno ($(du -sh map | cut -f1))"
