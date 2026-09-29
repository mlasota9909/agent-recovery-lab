#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
confirmed=false
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; --yes) confirmed=true ;; *) fail 'usage: 99-destroy-vm.sh --yes [--dry-run]' ;; esac
done
$confirmed || fail 'usage: 99-destroy-vm.sh --yes [--dry-run]'
load_config
require_local
lock_provision
# Never use undefine --remove-all-storage or delete disks by a name wildcard.
run python3 "$ROOT/provision/lib/provision.py" destroy
