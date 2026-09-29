#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/run/common.sh"
start_log 30-incident-gate
python3 "$ROOT/lib/lab_run.py" gate "$@"
