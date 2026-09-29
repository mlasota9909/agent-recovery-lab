# Honor caller-exported evidence/archive/results paths after sourcing etc/lab.env.
# Callers must set _LAB_OV_* from the pre-source environment, then source this file.
[ -n "${_LAB_OV_EVIDENCE_ROOT:-}" ] && EVIDENCE_ROOT="$_LAB_OV_EVIDENCE_ROOT"
[ -n "${_LAB_OV_ARCHIVE_ROOT:-}" ] && ARCHIVE_ROOT="$_LAB_OV_ARCHIVE_ROOT"
[ -n "${_LAB_OV_ARCHIVE_CURRENT:-}" ] && ARCHIVE_CURRENT="$_LAB_OV_ARCHIVE_CURRENT"
[ -n "${_LAB_OV_RESULTS_ROOT:-}" ] && RESULTS_ROOT="$_LAB_OV_RESULTS_ROOT"
export EVIDENCE_ROOT ARCHIVE_ROOT ARCHIVE_CURRENT RESULTS_ROOT
