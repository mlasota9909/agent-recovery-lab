#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/provision/common.sh"
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; *) fail 'usage: guest-base.sh [--dry-run]' ;; esac
done
load_config
lock_provision
require_replica
guest sudo -n bash -s -- "$PROVISION_USER" <<'REMOTE'
set -euo pipefail
cloud-init status --wait
packages=(zfsutils-linux postgresql-18 postgresql-18-wal2json python3 rsync openssh-client openssl)
missing=()
for package in "${packages[@]}"; do
  if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || :) != 'install ok installed' ]]; then
    missing+=("$package")
  fi
done
if (( ${#missing[@]} )); then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
fi
modprobe zfs
systemctl enable --now postgresql@18-main
# An absent host evidence path below the guest administrator's private home
# must fail at directory traversal for every victim principal.
chmod 0750 "$(getent passwd "$1" | cut -d: -f6)"
sudo -n -u postgres psql -X -Atqc 'SELECT 1'
REMOTE
