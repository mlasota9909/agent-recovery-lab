#!/usr/bin/env bash
# Retire an incident attempt in the study scope before any freeze, so stage 20 can
# run again. The attempt's records move to logs/superseded/<UTC time>/ with the
# stated reason; nothing is deleted. A frozen study is never retired.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $# -eq 1 && -n $1 ]] || { printf '%s\n' 'usage: run/retire-attempt.sh "<reason>"' >&2; exit 2; }
export LAB_RUN_SCOPE=run
source "$ROOT/run/common.sh"
start_log retire-attempt
[[ ! -e $ROOT/sdd/specs/P12-file-level-test/contracts/frozen-hashes.json ]] ||
  { printf '%s\n' 'A freeze exists; a frozen study is never retired' >&2; exit 1; }
[[ -f $ROOT/logs/run/incident-started.json ]] ||
  { printf '%s\n' 'No incident attempt to retire in logs/run' >&2; exit 1; }
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
dest=$ROOT/logs/superseded/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$dest"
incident=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("incident_id", ""))' \
  "$ROOT/logs/run/latest-incident.json" 2>/dev/null || true)
for name in incident-started.json incident-generation.json latest-incident.json; do
  [[ ! -e $ROOT/logs/run/$name ]] || mv "$ROOT/logs/run/$name" "$dest/"
done
[[ -z $incident || ! -d $ROOT/logs/run/$incident ]] || mv "$ROOT/logs/run/$incident" "$dest/"
find "$ROOT/logs/run" -maxdepth 1 -name '*-20-incident.log' -exec mv -t "$dest/" {} +
find "$ROOT/logs/run" -maxdepth 1 -name '*-30-incident-gate.log' -exec mv -t "$dest/" {} +
printf 'Retired before any freeze on %s.\nReason: %s\n' "$(date -u +%FT%TZ)" "$1" > "$dest/NOTE.txt"
printf 'Retired the attempt; records in %s\n' "${dest#"$ROOT"/}"
