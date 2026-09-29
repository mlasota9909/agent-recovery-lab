#!/usr/bin/env bash
# Rehearse incident generation and the incident gate in a separate log scope.
# A dry-run incident is never frozen, studied or compared.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $# -eq 0 ]] || { printf '%s\n' 'usage: run/dry-run.sh' >&2; exit 2; }
LAB_RUN_SCOPE=dry-run/$(date -u +%Y%m%dT%H%M%SZ)
export LAB_RUN_SCOPE
source "$ROOT/run/common.sh"
start_log dry-run
"$ROOT/run/20-incident.sh" --scenario SC-02
incident=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["incident_id"])' "$ROOT/logs/$LAB_RUN_SCOPE/latest-incident.json")
"$ROOT/run/30-incident-gate.sh" "$incident"
printf 'Dry run %s passed the incident gate; records in logs/%s\n' "$incident" "$LAB_RUN_SCOPE"
