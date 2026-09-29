#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
[[ -f $ROOT/etc/lab.local.env ]] || { printf '%s\n' 'Configure etc/lab.local.env first; see README.md' >&2; exit 2; }
set -a
source "$ROOT/etc/lab.env"
set +a
[[ $LAB_ROOT == "$ROOT" ]] || { printf '%s\n' 'LAB_ROOT must identify this checkout' >&2; exit 2; }
export PYTHONPATH="$ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
umask 077
mkdir -p "$ROOT/logs/run" "$ROOT/var/run"
if [[ ${RUN_LOCK_HELD:-} != "$ROOT" ]]; then
  exec 8>"$ROOT/var/run/lock"
  flock -n 8 || { printf '%s\n' 'Another run stage is active' >&2; exit 1; }
  export RUN_LOCK_HELD=$ROOT
fi

start_log() {
  local stage=$1
  RUN_LOG="$ROOT/logs/run/$(date -u +%Y%m%dT%H%M%S.%NZ)-$$-$stage.log"
  exec > >(tee -a "$RUN_LOG") 2>&1
  printf 'Stage %s; log %s\n' "$stage" "$RUN_LOG"
  trap 'rc=$?; printf "Exit %s at %s\n" "$rc" "$(date -u +%FT%TZ)"' EXIT
}
