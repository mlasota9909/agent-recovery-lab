#!/usr/bin/env bash
# Y003: repeated-key reconciliation soundness (clean bijection, injected gap+dup, revert).
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# shellcheck source=/dev/null
set -a
source "$ROOT/etc/lab.env"
set +a
export PYTHONPATH="$ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"

SEED="${SEED:-7}"
INJECT="${INJECT:-1}"
CAPTURE="${CAPTURE:-1}"
REVIEW="$ROOT/logs/review/Y003"
mkdir -p "$REVIEW"

die() { printf '%s\n' "$*" >&2; exit 1; }

c1_ok() {
  python3 - "$1" <<'PY'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
ops = int(rep["ops"])
mapped = int(rep["mapped"])
gaps = int(rep["gaps"])
dups = int(rep["duplicates"])
raise SystemExit(0 if ops == mapped and gaps == 0 and dups == 0 and ops > 0 else 1)
PY
}

account() {
  local inc=$1 dest=$2 rc
  set +e
  "$ROOT/bin/lab-ledger-account" "$inc" >"$dest"
  rc=$?
  set +e
  return "$rc"
}

# Plan determinism (Y003-6): same seed → identical compared fields.
python3 - <<PY
import json
from lab_capture_workload import plan_repeated_keys, compared_fields
a = [compared_fields(o) for o in plan_repeated_keys($SEED)]
b = [compared_fields(o) for o in plan_repeated_keys($SEED)]
assert a == b and len(a) >= 10
open("$REVIEW/plan-determinism.json", "w", encoding="utf-8").write(
    json.dumps({"seed": $SEED, "ops": len(a), "identical": True}, sort_keys=True) + "\n")
PY

if [[ $CAPTURE == 1 ]]; then
  "$ROOT/bin/lab-ready" >/dev/null
  new=$("$ROOT/bin/lab-incident" --new --scenario SC-01)
  INCIDENT=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["incident"])' "$new")
  printf '%s\n' "$INCIDENT" >"$REVIEW/incident.txt"
  for _ in $(seq 1 30); do
    if "$ROOT/bin/lab-consumer" status "$INCIDENT" >/dev/null 2>&1 \
       && "$ROOT/bin/lab-slot" --check >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  "$ROOT/bin/lab-heartbeat" --start >/dev/null
  "$ROOT/bin/lab-snapshot" --label y003_a >/dev/null
  sleep 1
  "$ROOT/bin/lab-snapshot" --label y003_b >/dev/null
  python3 - <<PY
from lab_capture import start_snapshot_loop
from lab_snapshot_tick import append_anchored_snapshot, ledger_path, load_array
inc = "$INCIDENT"
start_snapshot_loop(inc)
path = ledger_path(inc)
if not load_array(path):
    append_anchored_snapshot(inc)
PY
  python3 - <<PY
from lab_snapshot_tick import append_anchored_snapshot, ledger_path, load_array
inc = "$INCIDENT"
path = ledger_path(inc)
rows = load_array(path)
if not rows:
    append_anchored_snapshot(inc)
PY
  "$ROOT/bin/lab-capture-workload" "$INCIDENT" --profile repeated-keys --seed "$SEED" \
    | tee "$REVIEW/workload-apply.json"
  "$ROOT/bin/lab-barrier" >/dev/null
  sleep 2
else
  [[ -s $REVIEW/incident.txt ]] || die "precondition failed: CAPTURE!=1 and incident.txt missing"
  INCIDENT=$(cat "$REVIEW/incident.txt")
fi

EV=$(python3 -c 'from lab_paths import evidence_dir; print(evidence_dir("'"$INCIDENT"'"))')
DB="$EV/db.jsonl"
WL="$EV/workload.jsonl"
[[ -s $DB && -s $WL ]] || die "precondition failed: missing $DB or $WL"
if [[ $CAPTURE == 1 ]]; then
  cp -f "$DB" "$REVIEW/db.jsonl.pre_account"
  cp -f "$WL" "$REVIEW/workload.jsonl"
else
  [[ -s $REVIEW/db.jsonl.orig ]] || die "precondition failed: db.jsonl.orig missing for CAPTURE=0"
  cp -f "$REVIEW/db.jsonl.orig" "$DB"
fi
printf '%s\n' "$SEED" >"$REVIEW/seed.txt"

python3 - "$DB" "$REVIEW/xid-null-count.txt" <<'PY'
import json, sys
from lab_ledger_account import rec_key
from lab_paths import env
hb = env("HEARTBEAT_TABLE")
path, outp = sys.argv[1], sys.argv[2]
nulls = 0
ledgerable = 0
for line in open(path, encoding="utf-8"):
    if not line.strip():
        continue
    rec = json.loads(line)
    action, table = rec.get("action"), rec.get("table")
    if action in {"I", "U", "D", "T"} and table != hb:
        ledgerable += 1
        if rec.get("xid") is None:
            nulls += 1
open(outp, "w", encoding="utf-8").write(f"ledgerable={ledgerable}\nnull_xid={nulls}\n")
raise SystemExit(0 if nulls == 0 and ledgerable > 0 else 1)
PY

set +e
account "$INCIDENT" "$REVIEW/positive-reconcile.json"
pos_rc=$?
set -e
c1_ok "$REVIEW/positive-reconcile.json" || die "assertion failed: positive reconcile is not a clean bijection"

if [[ $INJECT != 1 ]]; then
  printf '%s\n' "negative phase did not run" >&2
  exit 1
fi

# Snapshot the live ledger immediately before mutation so heartbeats during
# C-5 do not make orig/corrupted line counts diverge for a reason other than inject.
cp -f "$DB" "$REVIEW/db.jsonl.orig"

python3 - "$DB" "$REVIEW/inject-choice.json" <<'PY'
import json, sys
from collections import defaultdict
from lab_ledger_account import rec_key

path, choice_path = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines()
groups = defaultdict(list)
for i, ln in enumerate(lines):
    if not ln.strip():
        continue
    rec = json.loads(ln)
    k = rec_key(rec)
    if k is None:
        continue
    kind = k[0]
    if kind != "DML":
        continue
    ident = (k[2], k[3], k[4])  # table, action, natural_key
    groups[ident].append((i, k[1], rec))

target = None
for ident, members in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2]))):
    xids = {m[1] for m in members}
    if len(members) >= 2 and len(xids) >= 2:
        target = (ident, members)
        break
if target is None:
    raise SystemExit("assertion failed: no shared natural key with two distinct xids")
ident, members = target
members = sorted(members, key=lambda m: (int(m[1]), m[0]))
remove_i, remove_xid, _ = members[0]
dup_i, dup_xid, dup_rec = members[1]
orig_n = len([ln for ln in lines if ln.strip()])
new_lines = [ln for i, ln in enumerate(lines) if i != remove_i]
new_lines.append(json.dumps(dup_rec, separators=(",", ":")))
new_n = len([ln for ln in new_lines if ln.strip()])
if new_n != orig_n:
    raise SystemExit(f"assertion failed: inject changed line count {orig_n}->{new_n}")
open(path, "w", encoding="utf-8").write("\n".join(new_lines) + "\n")
open(choice_path, "w", encoding="utf-8").write(json.dumps({
    "identity": {"table": ident[0], "action": ident[1], "natural_key": ident[2]},
    "removed_xid": remove_xid,
    "duplicated_xid": dup_xid,
    "removed_index": remove_i,
    "duplicated_index": dup_i,
    "line_count_before": orig_n,
    "line_count_after": new_n,
}, sort_keys=True, default=str) + "\n")
PY

orig_hash=$(sha256sum "$REVIEW/db.jsonl.orig" | awk '{print $1}')
live_hash=$(sha256sum "$DB" | awk '{print $1}')
if [[ $orig_hash == "$live_hash" ]]; then
  printf '%s\n' "negative phase did not run" >&2
  exit 1
fi

python3 - "$REVIEW/db.jsonl.orig" "$DB" "$WL" "$REVIEW/count-only-contrast.txt" "$REVIEW/inject-choice.json" <<'PY'
import json, sys
from pathlib import Path
from lab_ledger_account import rec_key, load_jsonl
orig, corrupted, wl, out, choice_path = sys.argv[1:]
choice = json.load(open(choice_path, encoding="utf-8"))
def n_ledgerable(path):
    return sum(1 for rec in load_jsonl(Path(path)) if rec_key(rec) is not None)
n_ops = len(load_jsonl(Path(wl)))
lines_orig = sum(1 for ln in open(orig, encoding="utf-8") if ln.strip())
lines_cor = sum(1 for ln in open(corrupted, encoding="utf-8") if ln.strip())
open(out, "w", encoding="utf-8").write(
    f"ops={n_ops}\n"
    f"ledgerable_orig={n_ledgerable(orig)}\n"
    f"ledgerable_corrupted={n_ledgerable(corrupted)}\n"
    f"db_lines_orig={lines_orig}\n"
    f"db_lines_corrupted={lines_cor}\n"
    f"line_counts_equal={str(lines_orig == lines_cor).lower()}\n"
    f"count_only_would_report={'clean' if lines_orig == lines_cor else 'dirty'}\n"
    f"injected_shared_key={choice['identity']}\n"
    f"removed_xid={choice['removed_xid']}\n"
    f"duplicated_xid={choice['duplicated_xid']}\n"
)
raise SystemExit(0 if lines_orig == lines_cor else 1)
PY

set +e
account "$INCIDENT" "$REVIEW/negative-reconcile.json"
neg_rc=$?
set -e
python3 - "$REVIEW/negative-reconcile.json" <<'PY'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
gaps, dups = int(rep["gaps"]), int(rep["duplicates"])
c1 = ((rep.get("rules") or {}).get("C-1") or {}).get("ok")
if gaps < 1 or dups < 1 or c1 is not False or rep.get("ok") is not False:
    raise SystemExit(f"assertion failed: injected fault not detected gaps={gaps} dups={dups} c1={c1} ok={rep.get('ok')}")
PY

cp -f "$REVIEW/db.jsonl.orig" "$DB"
set +e
account "$INCIDENT" "$REVIEW/revert-reconcile.json"
set -e
c1_ok "$REVIEW/revert-reconcile.json" || die "assertion failed: revert reconcile is not a clean bijection"

# Replay the same recorded mutation; gap/dup counts must match (Y003-6).
python3 - "$REVIEW/db.jsonl.orig" "$DB" "$REVIEW/inject-choice.json" <<'PY'
import json, sys
orig, dest, choice_path = sys.argv[1:]
choice = json.load(open(choice_path, encoding="utf-8"))
lines = open(orig, encoding="utf-8").read().splitlines()
remove_i = int(choice["removed_index"])
dup_i = int(choice["duplicated_index"])
dup_rec = json.loads(lines[dup_i])
new_lines = [ln for i, ln in enumerate(lines) if i != remove_i]
new_lines.append(json.dumps(dup_rec, separators=(",", ":")))
open(dest, "w", encoding="utf-8").write("\n".join(new_lines) + "\n")
PY
set +e
account "$INCIDENT" "$REVIEW/negative-reconcile-2.json"
set -e
python3 - "$REVIEW/negative-reconcile.json" "$REVIEW/negative-reconcile-2.json" <<'PY'
import json, sys
a, b = [json.load(open(p, encoding="utf-8")) for p in sys.argv[1:]]
assert a["gaps"] == b["gaps"] and a["duplicates"] == b["duplicates"]
assert a["gaps"] >= 1 and a["duplicates"] >= 1
PY
cp -f "$REVIEW/db.jsonl.orig" "$DB"

python3 - <<PY
import json
from pathlib import Path
review = Path("$REVIEW")
summary = {
    "ok": True,
    "incident": "$INCIDENT",
    "seed": $SEED,
}
for name in ("positive-reconcile.json", "negative-reconcile.json", "revert-reconcile.json"):
    rep = json.loads((review / name).read_text(encoding="utf-8"))
    key = name.split("-")[0]
    summary[key] = {k: rep.get(k) for k in ("ops", "mapped", "gaps", "duplicates", "ok")}
print(json.dumps(summary, sort_keys=True))
open("$REVIEW/summary.json", "w", encoding="utf-8").write(json.dumps(summary, sort_keys=True) + "\n")
PY
