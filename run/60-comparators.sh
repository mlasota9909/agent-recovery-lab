#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/run/common.sh"
start_log 60-comparators
python3 "$ROOT/lib/lab_run.py" comparators "$@"
