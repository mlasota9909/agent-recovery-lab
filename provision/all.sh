#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
host_args=() vm_args=()
for arg in "$@"; do
  case $arg in
    --dry-run) DRY_RUN=true ;;
    --install) host_args+=(--install) ;;
    --recreate) vm_args+=(--recreate) ;;
    *) fail 'usage: all.sh [--install] [--recreate] [--dry-run]' ;;
  esac
done
load_config
if $DRY_RUN; then
  "$ROOT/provision/00-host-check.sh" --dry-run "${host_args[@]}"
  "$ROOT/provision/10-create-vm.sh" --dry-run "${vm_args[@]}"
  for stage in 20-configure-guest 30-configure-host 40-healthcheck; do
    "$ROOT/provision/$stage.sh" --dry-run
  done
  exit 0
fi
lock_provision
install -d -m 0700 "$PROVISION_LOGS"
log=$(mktemp "$PROVISION_LOGS/all-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.log")
exec > >(tee -a "$log") 2>&1
trap 'rc=$?; printf "provision exit=%s log=%s\n" "$rc" "$log"' EXIT
"$ROOT/provision/00-host-check.sh" "${host_args[@]}"
"$ROOT/provision/10-create-vm.sh" "${vm_args[@]}"
"$ROOT/provision/20-configure-guest.sh"
"$ROOT/provision/30-configure-host.sh"
"$ROOT/provision/40-healthcheck.sh"
