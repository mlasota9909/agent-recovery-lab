#!/usr/bin/env bash
# Retire an incident attempt in the study scope before any freeze, so it can be
# generated again. The attempt's records move to logs/superseded/<UTC time>/ with
# the stated reason; nothing is deleted. A frozen study is never retired, except
# that an SC-03 or SC-04 attempt may be retired after its freeze with
# --after-freeze, for an engineering fault, with the calls already made recorded.
# --sc01 retires an attempt of the optional database-level replication;
# --sc03 and --sc04 retire attempts of the schema-change and scattered-update studies.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scenario=SC-02
after_freeze=0
usage() { printf '%s\n' 'usage: run/retire-attempt.sh [--sc01|--sc03|--sc04] [--after-freeze] "<reason>"' >&2; exit 2; }
while [[ ${1:-} == --* ]]; do
  case $1 in
    --sc01) scenario=SC-01 ;;
    --sc03) scenario=SC-03 ;;
    --sc04) scenario=SC-04 ;;
    --after-freeze) after_freeze=1 ;;
    *) usage ;;
  esac
  shift
done
[[ $# -eq 1 && -n $1 ]] || usage
if (( after_freeze )) && [[ $scenario != SC-03 && $scenario != SC-04 ]]; then
  printf '%s\n' '--after-freeze applies only to the SC-03 and SC-04 studies' >&2; exit 2
fi
export LAB_RUN_SCOPE=run
source "$ROOT/run/common.sh"
start_log retire-attempt
tag=$(printf '%s' "$scenario" | tr -d '-' | tr 'A-Z' 'a-z')
scope=$ROOT/logs/run
[[ $scenario == SC-02 ]] || scope=$ROOT/logs/run/$tag
[[ -f $scope/incident-started.json ]] ||
  { printf 'No %s incident attempt to retire in %s\n' "$scenario" "${scope#"$ROOT"/}" >&2; exit 1; }
incident=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("incident_id", ""))' \
  "$scope/latest-incident.json" 2>/dev/null || true)
if [[ $scenario == SC-02 ]]; then
  frozen=$ROOT/sdd/specs/P12-file-level-test/contracts/frozen-hashes.json
else
  frozen=$ROOT/logs/run/${incident:-none}/$tag/frozen-hashes.json
fi
if [[ -e $frozen ]] && (( ! after_freeze )); then
  printf '%s\n' 'A freeze exists; a frozen study is never retired' >&2; exit 1
fi
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
calls=0
rows=0
if [[ -n $incident && ( $scenario == SC-03 || $scenario == SC-04 ) ]]; then
  calls=$(find "$ROOT/logs/run/$incident/$tag/units" -name completion.txt 2>/dev/null | wc -l)
  for kind in study comparators; do
    result=$ROOT/results/$tag-$kind-$incident.jsonl
    if [[ -e $result ]]; then
      rows=$(( rows + $(wc -l < "$result") ))
      mv "$result" "$dest/"
    fi
  done
fi
for name in incident-started.json incident-generation.json latest-incident.json; do
  [[ ! -e $scope/$name ]] || mv "$scope/$name" "$dest/"
done
[[ -z $incident || ! -d $ROOT/logs/run/$incident ]] || mv "$ROOT/logs/run/$incident" "$dest/"
if [[ $scenario == SC-02 ]]; then
  find "$ROOT/logs/run" -maxdepth 1 \( -name '*-20-incident.log' -o -name '*-30-incident-gate.log' \) -exec mv -t "$dest/" {} +
elif [[ $scenario == SC-01 ]]; then
  find "$ROOT/logs/run" -maxdepth 1 -name '*-sc01-replication.log' -exec mv -t "$dest/" {} +
else
  find "$ROOT/logs/run" -maxdepth 1 -name "*-$tag-study.log" -exec mv -t "$dest/" {} +
fi
if [[ -e $frozen || -e $dest/${incident:-none}/$tag/frozen-hashes.json ]]; then
  when="after its freeze, with $calls model call(s) made and $rows result row(s) recorded, none used"
else
  when="before any freeze"
fi
printf 'Retired %s attempt %s %s on %s.\nReason: %s\n' \
  "$scenario" "${incident:-(no incident)}" "$when" "$(date -u +%FT%TZ)" "$1" > "$dest/NOTE.txt"
printf 'Retired the attempt; records in %s\n' "${dest#"$ROOT"/}"
