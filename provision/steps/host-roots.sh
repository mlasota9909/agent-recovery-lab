#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/provision/common.sh"
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; *) fail 'usage: host-roots.sh [--dry-run]' ;; esac
done
load_config
lock_provision
run python3 "$ROOT/provision/lib/provision.py" host-roots
