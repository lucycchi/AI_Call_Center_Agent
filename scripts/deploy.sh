#!/usr/bin/env bash
# Deploys the agent to Fly.io (Task 26, R22, R77):
#   1. the quick test run (python -m eval.quick_run; paid, test key), unless --skip-quick-run (only if it is cut);
#   2. scripts/fly deploy, which builds the image from the Dockerfile and releases it;
#   3. scripts/fly scale count 1 --yes, so exactly one machine runs (one worker, one volume);
#   4. scripts/fly status --json, which must show exactly one machine, or this script fails.
# Every Fly.io command goes through scripts/fly, which finds the Fly.io command line tool even when it is not on PATH.
# QUICK_RUN overrides the quick run command (the tests use a fake one).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
fly_cmd="$root/scripts/fly"

usage() { echo "usage: scripts/deploy.sh [--skip-quick-run]" >&2; }

skip_quick_run=0
for arg in "$@"; do
  case "$arg" in
    --skip-quick-run) skip_quick_run=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $arg" >&2; usage; exit 2 ;;
  esac
done

if [[ -x "$root/.venv/bin/python" ]]; then python_bin="$root/.venv/bin/python"; else python_bin="python3"; fi

if [[ "$skip_quick_run" == 1 ]]; then
  echo "== skipping the quick test run (--skip-quick-run)"
else
  echo "== quick test run"
  read -r -a quick_run <<< "${QUICK_RUN:-$python_bin -m eval.quick_run}"
  if ! "${quick_run[@]}"; then
    echo "the quick test run failed; not deploying" >&2
    exit 1
  fi
fi

echo "== deploy"
"$fly_cmd" deploy --ha=false

echo "== scale to one machine"
"$fly_cmd" scale count 1 --yes

echo "== check the machine count"
status="$("$fly_cmd" status --json)"
if ! count="$(printf '%s' "$status" | python3 -c '
import json, sys
data = json.load(sys.stdin)
machines = data if isinstance(data, list) else (data.get("Machines") or data.get("machines") or [])
print(len(machines))
')"; then
  echo "could not read the machine count from scripts/fly status --json" >&2
  exit 1
fi
if [[ "$count" != 1 ]]; then
  echo "expected exactly one machine, found $count; check scripts/fly status" >&2
  exit 1
fi

host="$(printf '%s' "$status" | python3 -c 'import json, sys; d = json.load(sys.stdin); print(d.get("Hostname", "") if isinstance(d, dict) else "")')"
echo "deployed: one machine running${host:+ at https://$host}"
