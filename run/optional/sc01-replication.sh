#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/run/common.sh"
start_log sc01-replication
python3 "$ROOT/lib/lab_sc01_replication.py" "$@"
