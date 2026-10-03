#!/usr/bin/env bash
# The whole experiment in one checkout and on one VM: the file-deletion study (SC-02, stages 00 to 70, which also
# provisions the VM on a first run), then the row-deletion (SC-01), schema-change (SC-03) and row-update (SC-04)
# studies. Stops at the first failure. After retiring a refused attempt (run/retire-attempt.sh), resume with
# --from sc02|sc01|sc03|sc04 to run that study and the ones after it.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
from=sc02
case ${1:-} in
  '') ;;
  --from) from=${2:-}; [[ $from =~ ^sc0[1234]$ ]] || { printf '%s\n' 'usage: run/experiment.sh [--from sc02|sc01|sc03|sc04]' >&2; exit 2; } ;;
  *) printf '%s\n' 'usage: run/experiment.sh [--from sc02|sc01|sc03|sc04]' >&2; exit 2 ;;
esac
source "$ROOT/run/common.sh"
start_log experiment
steps=(sc02 sc01 sc03 sc04)
declare -A script=([sc02]=run/all.sh [sc01]=run/optional/sc01-replication.sh
                   [sc03]=run/optional/sc03-study.sh [sc04]=run/optional/sc04-study.sh)
started=false
for step in "${steps[@]}"; do
  [[ $step == "$from" ]] && started=true
  $started || continue
  printf 'Experiment: %s (%s)\n' "$step" "${script[$step]}"
  "$ROOT/${script[$step]}"
done
printf '%s\n' 'Experiment: all four studies complete'
