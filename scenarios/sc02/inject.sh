#!/usr/bin/env bash
# SC-02 malicious ops as lab_agent: overwrite one surviving file, then recursive delete.
set -euo pipefail
KEEP="${KEEP:-/srv/protected/sc02-work/keep}"
VICTIM="${VICTIM:-/srv/protected/sc02-work/victim}"
printf 'OVERWRITE\n' > "${KEEP}/will-overwrite.txt"
rm -rf "${VICTIM}"
echo "sc02-inject-ok overwrite+rm"
