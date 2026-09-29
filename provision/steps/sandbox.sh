#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/provision/common.sh"
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; *) fail 'usage: sandbox.sh [--dry-run]' ;; esac
done
load_config
lock_provision
require_replica
guest sudo -n bash -s -- "$ZPOOL" "$SANDBOX_DATASET" "$SANDBOX_MNT" <<'REMOTE'
set -euo pipefail
pool=$1 dataset=$2 mountpoint=$3
[[ $(zfs get -H -o value compression "$pool") == lz4 ]]
[[ $(zfs get -H -o value recordsize "$pool") == 128K ]]
if zfs list -H -o name "$dataset" >/dev/null 2>&1; then
  [[ $(zfs get -H -o value mountpoint "$dataset") == "$mountpoint" ]]
else
  zfs create -o mountpoint="$mountpoint" "$dataset"
fi
REMOTE
