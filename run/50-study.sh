#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/run/common.sh"
start_log 50-study
python3 "$ROOT/lib/lab_run.py" study "$@"
