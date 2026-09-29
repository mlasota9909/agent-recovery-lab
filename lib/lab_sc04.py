"""SC-04 stealthy randomized UPDATEs + precision/recall harness."""
from __future__ import annotations

import json
import random
import time

from lab_p3_util import EXIT_ASSERT, die, ssh_psql, utc_now, write_json, write_jsonl
from lab_paths import env, evidence_dir, lab_root
from lab_p7_app import DmlLoop
from lsn import lsn_int, lsn_norm

REL = "sc04_items"
MALICIOUS_N = 12
SEED = 42


def _pg(sql: str, role: str | None = None) -> str:
    proc = ssh_psql(sql, role=role)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: psql: {proc.stderr.strip()[-1500:]}")
    return proc.stdout.strip()


def prepare(incident: str) -> dict:
    sql = f"""
DROP TABLE IF EXISTS public.{REL};
CREATE TABLE public.{REL} (
  id bigint PRIMARY KEY,
  payload text NOT NULL
);
ALTER TABLE public.{REL} REPLICA IDENTITY FULL;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.{REL} TO lab_app;
GRANT SELECT, UPDATE ON public.{REL} TO lab_agent;
INSERT INTO public.{REL}(id, payload)
SELECT g, 'legit-' || g FROM generate_series(1, 200) g;
"""
    proc = ssh_psql(sql)
    if proc.returncode != 0:
        die(EXIT_ASSERT, f"assertion failed: SC-04 seed: {proc.stderr.strip()[-1500:]}")
    return {
        "baseline_s": 6,
        "after_s": 4,
        "tps": 10.0,
        "mix": "lab_app-high-volume-update+lab_agent-randomized-small-update",
        "relation": REL,
        "baseline_started": utc_now(),
    }


def start_confounder(incident: str) -> dict:
    app = DmlLoop(
        f"UPDATE public.{REL} SET payload = payload || '.' WHERE id = {{id}};",
        10.0, REL, id_mod=200,
    )
    app.start()
    return {"app": app, "incident": incident}


def stop_confounder(handle: dict) -> list[dict]:
    rows = handle["app"].stop()
    if len(rows) < 8:
        die(EXIT_ASSERT, "assertion failed: SC-04 confounder too small to hide malicious updates")
    return rows


def inject(incident: str) -> dict:
    ed = evidence_dir(incident)
    rng = random.Random(SEED)
    ids = rng.sample(range(1, 201), MALICIOUS_N)
    rng.shuffle(ids)
    delays = [rng.uniform(0.3, 1.4) for _ in ids]
    ops = []
    window_start = None
    sql_file = (lab_root() / "scenarios" / "sc04" / "inject.sql").read_text(encoding="utf-8")
    for i, rid in enumerate(ids):
        time.sleep(delays[i])
        lsn_before = lsn_norm(_pg("SELECT pg_current_wal_lsn();").upper())
        if window_start is None:
            window_start = lsn_before
        stmt = sql_file.replace(":id", str(rid)).replace(":marker", f"'mal-{rid}'")
        out = _pg(
            "SELECT current_user;\nBEGIN;\n"
            + stmt.strip().rstrip(";") + ";\n"
            "SELECT txid_current();\nSELECT pg_current_wal_lsn();\nCOMMIT;\n",
            role=env("ROLE_AGENT"),
        )
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not lines or lines[0] != env("ROLE_AGENT"):
            die(EXIT_ASSERT, f"assertion failed: SC-04 update not as lab_agent: {lines[:3]!r}")
        xid = int(lines[-2]) & 0xFFFFFFFF
        lsn_end = lsn_norm(lines[-1].upper())
        ops.append({
            "row_id": rid,
            "xid": xid,
            "commit_lsn": lsn_end,
            "lsn_before": lsn_before,
            "t": utc_now(),
            "principal": env("ROLE_AGENT"),
        })
    earliest = min(ops, key=lambda o: lsn_int(o["commit_lsn"]))
    rec = {
        "incident": incident,
        "scenario_id": "SC-04",
        "principal": env("ROLE_AGENT"),
        "t_start": ops[0]["t"],
        "t_end": ops[-1]["t"],
        "lsn_start": window_start,
        "lsn_end": ops[-1]["commit_lsn"],
        "commit_lsn": earliest["commit_lsn"],
        "timing_pattern": "randomized",
        "ops": ops,
        "malicious_set": [{"row_id": o["row_id"], "xid": o["xid"]} for o in ops],
        "earliest_malicious_commit_lsn": earliest["commit_lsn"],
        "seed": SEED,
    }
    write_json(ed / "injection.json", rec)
    write_json(ed / "injection_log.json", rec)
    return rec


def score_identified(ground: list[dict], identified: list[dict]) -> dict:
    truth = {(int(x["row_id"]), int(x["xid"])) for x in ground}
    pred = {(int(x["row_id"]), int(x["xid"])) for x in identified}
    tp = len(truth & pred)
    fp = len(pred - truth)
    fn = len(truth - pred)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall,
        "n_truth": len(truth), "n_pred": len(pred),
    }


def identified_from_bound(incident: str, chosen_lsn: str) -> list[dict]:
    """Predicted malicious set = scripted malicious ops with commit_lsn >= chosen.

    Arms emit a coordinate, not a set. The bound interpretation treats everything
    at-or-after the chosen LSN as the identified damage (restore would undo it).
    Matching is against the known (row_id, xid) set from the injection log.
    """
    inj = json.loads((evidence_dir(incident) / "injection.json").read_text(encoding="utf-8"))
    cut = lsn_int(lsn_norm(chosen_lsn))
    out = []
    for op in inj["ops"]:
        if lsn_int(op["commit_lsn"]) >= cut:
            out.append({"row_id": op["row_id"], "xid": op["xid"]})
    return out


def earliest_bounded(incident: str, chosen_lsn: str) -> dict:
    inj = json.loads((evidence_dir(incident) / "injection.json").read_text(encoding="utf-8"))
    earliest = inj["earliest_malicious_commit_lsn"]
    cut = lsn_int(lsn_norm(chosen_lsn))
    earliest_n = lsn_int(lsn_norm(earliest))
    correctly = cut <= earliest_n
    return {
        "earliest_malicious_commit_lsn": earliest,
        "chosen_lsn": lsn_norm(chosen_lsn),
        "correctly_bounded": correctly,
        "earliest_bounded_commit": earliest if correctly else None,
    }


def oracle(incident: str, inj: dict, app_rows: list, open_snap: dict, pre: dict, post: dict) -> dict:
    from lab_p7 import resolve_lsn
    ed = evidence_dir(incident)
    earliest = inj["earliest_malicious_commit_lsn"]
    coord = resolve_lsn(lsn_norm(inj["ops"][0]["lsn_before"]))
    payload = {
        "coordinate": coord,
        "malicious_set": inj["malicious_set"],
        "earliest_malicious_commit_lsn": earliest,
        "n_malicious": len(inj["malicious_set"]),
        "computed_from": "scripted injection log of committed malicious UPDATEs",
        "incident_extra": {
            "earliest_malicious_commit_lsn": earliest,
            "n_malicious": len(inj["malicious_set"]),
        },
    }
    man = []
    for rec in app_rows or []:
        if rec.get("commit_lsn"):
            man.append({
                "commit_lsn": rec["commit_lsn"],
                "commit_ts": rec.get("wall_clock"),
                "operation": rec.get("operation"),
                "relation": rec.get("relation") or rec.get("table"),
                "row_ids": rec.get("row_ids") or [],
                "row_count": rec.get("row_count") or 1,
                "principal": rec.get("principal"),
            })
    write_jsonl(ed / "workload-manifest.jsonl", man)
    write_json(ed / "oracle.json", {"incident": incident, "coordinate": coord, "sc04": payload})
    write_json(ed / "sc04-groundtruth.json", {
        "malicious_set": inj["malicious_set"],
        "earliest_malicious_commit_lsn": earliest,
        "ops": inj["ops"],
    })
    return payload
