#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/run/common.sh"
start_log all
[[ $# -eq 0 ]] || { printf '%s\n' 'usage: run/all.sh (resume through individual stages)' >&2; exit 2; }
"$ROOT/run/00-provision.sh"
"$ROOT/run/10-preflight.sh"
"$ROOT/run/20-incident.sh" --scenario SC-02
incident=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["incident_id"])' "$ROOT/logs/run/latest-incident.json")
"$ROOT/run/30-incident-gate.sh" "$incident"
"$ROOT/run/40-freeze.sh" "$incident"
"$ROOT/run/50-study.sh" "$incident"
"$ROOT/run/60-comparators.sh" "$incident"
"$ROOT/run/70-analysis.sh"
