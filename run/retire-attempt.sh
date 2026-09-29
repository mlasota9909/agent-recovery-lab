#!/usr/bin/env bash
# Retire an incident attempt in the study scope before any freeze, so it can be
# generated again. The attempt's records move to logs/superseded/<UTC time>/ with
# the stated reason; nothing is deleted. A frozen study is never retired.
# --sc01 retires an attempt of the optional database-level replication.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scenario=SC-02
if [[ ${1:-} == --sc01 ]]; then scenario=SC-01; shift; fi
[[ $# -eq 1 && -n $1 ]] || { printf '%s\n' 'usage: run/retire-attempt.sh [--sc01] "<reason>"' >&2; exit 2; }
export LAB_RUN_SCOPE=run
source "$ROOT/run/common.sh"
start_log retire-attempt
scope=$ROOT/logs/run
[[ $scenario == SC-02 ]] || scope=$ROOT/logs/run/sc01
[[ -f $scope/incident-started.json ]] ||
  { printf 'No %s incident attempt to retire in %s\n' "$scenario" "${scope#"$ROOT"/}" >&2; exit 1; }
incident=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("incident_id", ""))' \
  "$scope/latest-incident.json" 2>/dev/null || true)
if [[ $scenario == SC-02 ]]; then
  frozen=$ROOT/sdd/specs/P12-file-level-test/contracts/frozen-hashes.json
else
  frozen=$ROOT/logs/run/${incident:-none}/sc01/frozen-hashes.json
fi
[[ ! -e $frozen ]] || { printf '%s\n' 'A freeze exists; a frozen study is never retired' >&2; exit 1; }
status=0
python3 - <<'PY' || status=$?
import sys
sys.path.insert(0, "lib")
import lab_run
try:
    lab_run.ensure_no_open_incident()
except ValueError:
    sys.exit(3)
PY
if (( status == 3 )); then
  "$ROOT/bin/lab-incident" --close >/dev/null
elif (( status != 0 )); then
  exit "$status"
fi
[[ -z $incident ]] || "$ROOT/bin/lab-consumer" stop "$incident" >/dev/null
dest=$ROOT/logs/superseded/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$dest"
for name in incident-started.json incident-generation.json latest-incident.json; do
  [[ ! -e $scope/$name ]] || mv "$scope/$name" "$dest/"
done
[[ -z $incident || ! -d $ROOT/logs/run/$incident ]] || mv "$ROOT/logs/run/$incident" "$dest/"
if [[ $scenario == SC-02 ]]; then
  find "$ROOT/logs/run" -maxdepth 1 \( -name '*-20-incident.log' -o -name '*-30-incident-gate.log' \) -exec mv -t "$dest/" {} +
else
  find "$ROOT/logs/run" -maxdepth 1 -name '*-sc01-replication.log' -exec mv -t "$dest/" {} +
fi
printf 'Retired %s attempt %s before any freeze on %s.\nReason: %s\n' \
  "$scenario" "${incident:-(no incident)}" "$(date -u +%FT%TZ)" "$1" > "$dest/NOTE.txt"
printf 'Retired the attempt; records in %s\n' "${dest#"$ROOT"/}"
