#!/usr/bin/env bash
# Container start (R77): on the first start the volume at /data is empty, so the live scheduling database begins as a
# copy of the seed shipped in the image. An existing live database is never overwritten. Then runs the given command.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
seed="$here/call_data/scheduling_db/meridian_scheduling.sqlite"
live="${DATABASE_PATH:?DATABASE_PATH must be set}"

mkdir -p "$(dirname "$live")"
if [[ -n "${OPS_DATABASE_PATH:-}" ]]; then
  mkdir -p "$(dirname "$OPS_DATABASE_PATH")"
fi
if [[ ! -e "$live" ]]; then
  cp "$seed" "$live.partial"
  mv "$live.partial" "$live"
  echo "first start: copied the seed scheduling database to $live"
fi

exec "$@"
