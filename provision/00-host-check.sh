#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
install_missing=false
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; --install) install_missing=true ;; *) fail 'usage: 00-host-check.sh [--install] [--dry-run]' ;; esac
done
load_config
if $DRY_RUN; then
  show python3 "$ROOT/provision/lib/provision.py" host-check
  if $install_missing; then show sudo -n apt-get install '<missing apt packages reported by host-check>'; fi
  exit 0
fi
if $install_missing; then support host-install; fi
support host-check
