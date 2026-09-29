#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; *) fail 'usage: 20-configure-guest.sh [--dry-run]' ;; esac
done
load_config
lock_provision
require_replica
step guest-base.sh
run "$ROOT/bin/lab-discover"                              # T001 writes only site overrides.
if ! $DRY_RUN; then load_config; fi
run "$ROOT/bin/lab-zfs-init"                              # T002
step sandbox.sh
run "$ROOT/bin/lab-pgdata-relocate"                       # T003
run "$ROOT/bin/lab-schema-init"                           # T004
# T005 must precede T006. Stage 30 shares these idempotent prerequisites.
step host-roots.sh
step wal-channel.sh
run "$ROOT/bin/lab-wal-config"                            # T006
run "$ROOT/bin/lab-slot" --create                         # T007
run "$ROOT/bin/lab-identities"                            # T008
run "$ROOT/bin/lab-heartbeat" --start                     # T010
step consumer-unit.sh
step baseline.sh                                         # T011/T012 prerequisites
# T009 needs the live append channel and active archive scope.
run "$ROOT/bin/lab-isolation-test"
