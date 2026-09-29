#!/usr/bin/env bash
# Shared functions; entry points own argument parsing and execution.
set -euo pipefail
PROVISION_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ROOT=$PROVISION_ROOT
DRY_RUN=false

fail() { printf '%s\n' "$*" >&2; exit 1; }
show() { printf '+'; printf ' %q' "$@"; printf '\n'; }
run() { if $DRY_RUN; then show "$@"; else "$@"; fi; }
support() { python3 "$ROOT/provision/lib/provision.py" "$@"; }

load_config() {
  # shellcheck source=/dev/null
  source "$ROOT/etc/lab.env"
  [[ $LAB_ROOT == "$ROOT" ]] || fail 'LAB_ROOT must identify this checkout'
  PROVISION_STORAGE_POOL=${PROVISION_STORAGE_POOL:-}
  PROVISION_SSH_KEY=${PROVISION_SSH_KEY:-$HOME/.ssh/id_ed25519}
  PROVISION_WAIT_SECONDS=${PROVISION_WAIT_SECONDS:-1800}
  PROVISION_STATE="$ROOT/var/provision"
  PROVISION_LOGS="$ROOT/logs/provision"
  [[ $PROVISION_USER == "$(id -un)" ]] || fail 'PROVISION_USER must be the invoking host account'
  [[ $PROVISION_USER != root ]] || fail 'Run provisioning as the host user with passwordless sudo'
  [[ $HOST_ARCHIVE_USER == "$PROVISION_USER" ]] || fail 'HOST_ARCHIVE_USER must be the invoking host user'
  [[ $VM_NAME =~ ^[a-zA-Z][a-zA-Z0-9-]{0,62}$ ]] || fail 'VM_NAME must be a hostname (letters, digits, hyphens)'
  [[ $PROVISION_WAIT_SECONDS =~ ^[1-9][0-9]*$ ]] || fail 'PROVISION_WAIT_SECONDS must be a positive integer'
  [[ $PG_VERSION == 18 ]] || fail 'This build requires PostgreSQL 18'
  [[ $DEV_SYSTEM =~ ^/dev/vd[a-z]+$ && $DEV_A =~ ^/dev/vd[a-z]+$ && $DEV_B =~ ^/dev/vd[a-z]+$ ]] || fail 'Configure virtio guest devices in etc/lab.local.env'
  [[ $DEV_SYSTEM != "$DEV_A" && $DEV_SYSTEM != "$DEV_B" && $DEV_A != "$DEV_B" ]] || fail 'Guest devices must be distinct'
  [[ -z ${LAB_ACTIVE_INCIDENT:-} ]] || fail 'Unset LAB_ACTIVE_INCIDENT before provisioning'
}

require_local() {
  [[ -f $ROOT/etc/lab.local.env ]] || fail 'Missing etc/lab.local.env; copy etc/lab.local.env.example and set VM_NAME, PROVISION_STORAGE_POOL and PROVISION_SSH_KEY'
  [[ $PROVISION_STORAGE_POOL =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || fail 'Set PROVISION_STORAGE_POOL in etc/lab.local.env'
}

# Quote a complete remote argv before handing it to SSH's command string.
guest() {
  local remote
  printf -v remote '%q ' "$@"
  if $DRY_RUN; then
    show ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 "$VM_SSH" "$remote"
    cat
  else
    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 "$VM_SSH" "$remote"
  fi
}

step() {
  local script=$1
  shift
  if $DRY_RUN; then "$ROOT/provision/steps/$script" --dry-run "$@"; else "$ROOT/provision/steps/$script" "$@"; fi
}

require_replica() {
  require_local
  if ! $DRY_RUN; then support check-domain; support check-scope; fi
}

# Serialize this checkout's builds; check-scope refuses an active experiment.
lock_provision() {
  if ! $DRY_RUN && [[ ${PROVISION_LOCK_HELD:-} != "$ROOT" ]]; then
    install -d -m 0700 "$PROVISION_STATE"
    exec 9>"$PROVISION_STATE/lock"
    flock -n 9 || fail 'Another provisioning operation holds var/provision/lock'
    export PROVISION_LOCK_HELD=$ROOT
  fi
}
