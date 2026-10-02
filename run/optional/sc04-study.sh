#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/run/common.sh"
start_log sc04-study
python3 "$ROOT/lib/lab_dbscen_study.py" --scenario SC-04 "$@"
