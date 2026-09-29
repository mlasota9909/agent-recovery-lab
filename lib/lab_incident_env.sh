#!/usr/bin/env bash
# Select per-incident runtime after etc/lab.env. Banked/legacy incidents remain unchanged.
lab_incident_env_select() {
  local lab_root=${LAB_ROOT:-$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
  local requested=${LAB_ACTIVE_INCIDENT:-} runtime_root="$lab_root/runtime/incidents" runtime_file= line key value
  if [[ -z $requested && -n ${ARCHIVE_CURRENT:-} && -L ${ARCHIVE_CURRENT:-} ]]; then
    requested=$(basename -- "$(readlink -f -- "$ARCHIVE_CURRENT")")
  fi
  [[ -n $requested ]] || return 0
  if [[ $requested == SC-01_20260824T091611Z || $requested == i_20260824T091611Z_122142 ]]; then
    [[ -z ${LAB_ACTIVE_INCIDENT:-} ]] || {
      printf '%s\n' 'precondition failed: SC-01 is banked and has no incident runtime' >&2
      return 2
    }
    return 0
  fi
  # Pre-isolation SC-01 captures have no runtime record and retain the shared
  # P0-P7 substrate. Only P7.1 SC-02/03/04 incidents require isolated records.
  [[ $requested == SC-01_* ]] && return 0
  if [[ -f "$runtime_root/$requested.env" ]]; then
    runtime_file="$runtime_root/$requested.env"
  elif [[ -d $runtime_root ]]; then
    local candidate
    for candidate in "$runtime_root"/*.env; do
      [[ -f $candidate ]] || continue
      while IFS= read -r line; do
        if [[ $line == "ARCHIVE_INCIDENT=$requested" ]]; then runtime_file=$candidate; break 2; fi
      done <"$candidate"
    done
  fi
  if [[ -z ${runtime_file:-} || ! -f $runtime_file ]]; then
    [[ -z ${LAB_ACTIVE_INCIDENT:-} ]] && return 0
    printf 'precondition failed: runtime record absent for %s\n' "$requested" >&2
    return 2
  fi
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^([A-Z][A-Z0-9_]*)=([A-Za-z0-9_./:-]+)$ ]] || {
      printf 'assertion failed: unsafe incident runtime line in %s\n' "$runtime_file" >&2
      return 1
    }
    key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}
    case $key in
      ARCHIVE_INCIDENT|INC_ID|INC_DS|INC_PGDATA|INC_PROTECTED|INC_PG_PORT|INC_PG_SOCKET|INC_SLOT|INC_HEARTBEAT_PORT) ;;
      *) printf 'assertion failed: unknown incident runtime key %s\n' "$key" >&2; return 1 ;;
    esac
    printf -v "$key" '%s' "$value"; export "$key"
  done <"$runtime_file"
  [[ ${ARCHIVE_INCIDENT:-} == "$requested" || ${INC_ID:-} == "$requested" ]] || {
    printf 'assertion failed: runtime record does not identify %s\n' "$requested" >&2; return 1;
  }
  DS_PARENT=$INC_DS
  DS_PGDATA=$INC_DS/pgdata
  DS_PROTECTED=$INC_DS/protected
  PG_DATA=$INC_PGDATA
  PG_PORT=$INC_PG_PORT
  MNT_PROTECTED=$INC_PROTECTED
  SLOT_NAME=$INC_SLOT
  export DS_PARENT DS_PGDATA DS_PROTECTED PG_DATA PG_PORT MNT_PROTECTED SLOT_NAME
}

lab_incident_env_select
