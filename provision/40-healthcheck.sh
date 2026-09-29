#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; *) fail 'usage: 40-healthcheck.sh [--dry-run]' ;; esac
done
load_config
require_local
lock_provision
# The fresh suite checks replica ownership too and records even a failed check.
run python3 "$ROOT/provision/lib/healthcheck.py"
