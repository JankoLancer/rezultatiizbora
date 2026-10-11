#!/usr/bin/env bash
# Prepare map/ for serving from the repo (no Docker):
#   map/data.json.gz  ->  map/data.json
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f map/data.json.gz ] && [ ! -f map/data.json ]; then
  gzip -dkf map/data.json.gz
fi
echo "OK: map/ spremno ($(du -sh map | cut -f1))"
