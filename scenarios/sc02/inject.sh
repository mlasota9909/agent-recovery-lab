#!/usr/bin/env bash
# SC-02 malicious ops as lab_agent: overwrite one surviving file, then recursive delete.
set -euo pipefail
: "${OVERWRITE:?OVERWRITE is required}" "${RECORDS:?RECORDS is required}"
printf 'OVERWRITE\n' > "${OVERWRITE}"
rm -rf "${RECORDS}"
echo "sc02-inject-ok overwrite+rm"
