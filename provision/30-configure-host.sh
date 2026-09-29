#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; *) fail 'usage: 30-configure-host.sh [--dry-run]' ;; esac
done
load_config
lock_provision
require_replica
step host-roots.sh
step wal-channel.sh
# T006 discovers the actual host source address and grants only that /32.
run "$ROOT/bin/lab-wal-config"
run "$ROOT/bin/lab-slot" --create
step consumer-unit.sh
step baseline.sh
