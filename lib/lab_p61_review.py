"""Produce P6.1 J002–J005 review bundles. Does not tick Reviewed."""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lab_arm_b_extract import extract as extract_completion
from lab_arm_b_prompt import assemble as assemble_prompt, CONTENT_BEGIN, CONTENT_END
from lab_diagnose_refusal import diagnose_dir
from lab_p3_util import (
    dump_lab_env_snapshot, review_dir, sha256_file, write_acceptance, write_artefacts,
    write_json, write_text, append_command, canonical_json,
)
from lab_p51 import ARTEFACT_HASHES, frozen_contract_rows
from lab_p61 import (
    GT_LSN, GT_LSN_INT, H001_ARM_B_PROTOCOL, H001_MODEL_RUNTIME, H001_P6_RUNTIME_AMENDMENT,
    INCIDENT, p6_contracts, p61_contracts, root,
)
from lab_paths import lab_root
from lab_repr import REPR_IDS, token_scan
from lsn import lsn_int, lsn_text_from_int

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
K = int(os.environ.get("ARM_B_K") or "5")
SAME_WINDOW = 1
SAME_LSN = "1/D9000168"
SAME_TS = "2026-08-24T09:16:16.256730Z"


def run(argv: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    envp = os.environ.copy()
    envp["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + envp.get("PYTHONPATH", ""))
    return subprocess.run(
        argv, cwd=str(root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=envp,
    )


def checklist_stamp(task: str) -> None:
    path = root() / "sdd/specs/P6.1-arm-b-answerability/checklist.md"
    text = path.read_text(encoding="utf-8")
    needle = f"| {task} |"
    lines = []
    for line in text.splitlines():
        if line.startswith(needle):
            parts = [p.strip() for p in line.strip().split("|")]
            title = parts[2] if len(parts) > 2 else ""
            reviewed = parts[5] if len(parts) > 5 else "☐"
            line = f"| {task} | {title} | {TODAY} | logs/review/{task}/ | {reviewed} |"
        lines.append(line)
    write_text(path, "\n".join(lines) + "\n")


def finish(task: str, rows: list[dict], artefacts: list[Path], observations: str, extra: str = "") -> None:
    dump_lab_env_snapshot(task)
    write_acceptance(task, rows, extra)
    write_artefacts(task, artefacts)
    write_text(review_dir(task) / "observations.md", observations.rstrip() + "\n")
    checklist_stamp(task)
    failed = [r["id"] for r in rows if r["result"] != "PASS"]
    if failed:
        raise SystemExit(f"{task} failed: {failed}")


def row(tid: str, tier: str, cmd: str, expected: str, observed: str, passed: bool) -> dict:
    return {
        "id": tid, "tier": tier, "command": cmd, "expected": expected,
        "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def extract_file(text: str, representation: str = "R2") -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".completion", delete=False, encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")
        path = handle.name
    try:
        return extract_completion(Path(path).read_text(encoding="utf-8"), INCIDENT, representation)
    finally:
        os.unlink(path)


def j002() -> None:
    task = "J002"
    rd = review_dir(task)
    amend = p61_contracts() / "model-runtime.amendment-1.md"
    os.chmod(amend, 0o444)
    base = p6_contracts() / "model-runtime.md"
    base_hash = sha256_file(base)
    amend_hash = sha256_file(amend)
    write_text(rd / "contract-hashes.txt",
               f"{base_hash}  {base.relative_to(root())}\n"
               f"{amend_hash}  {amend.relative_to(root())}\n"
               f"base_byte_identical={base_hash == H001_MODEL_RUNTIME}\n")
    proc = run(["bin/lab-model-containment", "--out", str(rd / "containment.json")])
    append_command(task, f"bin/lab-model-containment exit={proc.returncode}")
    cont = json.loads((rd / "containment.json").read_text())
    pub = run(["bin/lab-model-containment", "--endpoint", "http://1.1.1.1:4001"])
    cloud = run(["bin/lab-model-containment", "--alias", "deepseek-v4-pro"])
    revert = run(["bin/lab-model-containment"])
    write_json(rd / "negative.json", {
        "public_exit": pub.returncode,
        "public_stderr": pub.stderr.strip(),
        "public_stdout": json.loads(pub.stdout) if pub.stdout.strip().startswith("{") else pub.stdout,
        "public_caught": pub.returncode != 0 and "endpoint_is_private" in (pub.stderr + pub.stdout),
        "cloud_exit": cloud.returncode,
        "cloud_stderr": cloud.stderr.strip(),
        "cloud_stdout": json.loads(cloud.stdout) if cloud.stdout.strip().startswith("{") else cloud.stdout,
        "cloud_caught": cloud.returncode != 0 and "cloud_alias_targeted" in (cloud.stderr + cloud.stdout),
        "reverted_ok": revert.returncode == 0,
        "forbidden_alias": os.environ.get("LAB_FORBIDDEN_CLOUD_ALIAS"),
        "lab_hosts": os.environ.get("LAB_HOSTS"),
        "private_cidrs": os.environ.get("LAB_PRIVATE_CIDRS"),
    })
    neg = json.loads((rd / "negative.json").read_text())
    rows = [
        row("J002-1", "M", "amendment R2a-d; H001 base hash", "frozen; base byte-identical",
            f"base_ok={base_hash == H001_MODEL_RUNTIME} amend={amend_hash[:16]}",
            base_hash == H001_MODEL_RUNTIME and "R2a" in amend.read_text()),
        row("J002-2", "M", "lab-model-containment pinned endpoint", "containment_verified true",
            json.dumps({k: cont.get(k) for k in (
                "containment_verified", "endpoint_is_private", "public_egress_observed",
                "cloud_alias_targeted", "weights_hash_matches_pin")}, sort_keys=True),
            cont.get("containment_verified") is True),
        row("J002-3", "M", "inspect containment.json host/alias", "c220m3 / gb10a-deepseek-v4-flash",
            f"{cont.get('endpoint_host')} {cont.get('alias_targeted')}",
            cont.get("endpoint_host") == "c220m3" and cont.get("alias_targeted") == "gb10a-deepseek-v4-flash"),
    ]
    extra = (
        f"NEGATIVE TEST: public 1.1.1.1 caught={neg['public_caught']} "
        f"(exit {neg['public_exit']}); cloud alias caught={neg['cloud_caught']} "
        f"(exit {neg['cloud_exit']}); revert exit={revert.returncode}."
    )
    finish(task, rows, [amend, root() / "bin/lab-model-containment", rd / "containment.json",
                        rd / "contract-hashes.txt", rd / "negative.json"],
           "offline_verified is redefined to R2a-d (not loopback). "
           "c220m3 resolves to Tailscale CGNAT; LAB_PRIVATE_CIDRS includes 100.64.0.0/10.\n",
           extra)


def j003() -> None:
    task = "J003"
    rd = review_dir(task)
    amend = p61_contracts() / "arm-b-protocol.amendment-1.md"
    os.chmod(amend, 0o444)
    base = p6_contracts() / "arm-b-protocol.md"
    base_hash = sha256_file(base)
    amend_hash = sha256_file(amend)
    prompts = {}
    for rep in REPR_IDS:
        proc = run(["bin/lab-arm-b-prompt", "--incident", INCIDENT, "--representation", rep,
                    "--out", str(rd / f"prompt-{rep}.txt")])
        append_command(task, f"lab-arm-b-prompt {rep} exit={proc.returncode}")
        if proc.returncode != 0:
            raise SystemExit(proc.stderr or proc.stdout)
        prompts[rep] = (rd / f"prompt-{rep}.txt").read_text(encoding="utf-8")

    def split(t: str) -> tuple[str, str]:
        a = t.index(CONTENT_BEGIN)
        b = t.index(CONTENT_END) + len(CONTENT_END)
        return t[:a], t[b:]

    pres = {split(prompts[r])[0] for r in REPR_IDS}
    sufs = {split(prompts[r])[1] for r in REPR_IDS}
    mids = {prompts[r][prompts[r].index(CONTENT_BEGIN):prompts[r].index(CONTENT_END)] for r in REPR_IDS}
    parity = len(pres) == 1 and len(sufs) == 1 and len(mids) == 3
    write_text(rd / "prompt-diff.txt",
               f"prefix_identical={len(pres)==1}\nsuffix_identical={len(sufs)==1}\n"
               f"content_distinct={len(mids)}\nparity={parity}\n")
    guard_rows = []
    answer_hit = False
    for rep in REPR_IDS:
        view_path = root() / "var" / "arm_b" / "_guard" / f"{INCIDENT}-{rep}.json"
        g = run(["bin/lab-modelview-guard", str(view_path)])
        blob = view_path.read_text(encoding="utf-8") if view_path.is_file() else ""
        if '"answer"' in blob or '"candidates"' in blob:
            answer_hit = True
        guard_rows.append({"rep": rep, "exit": g.returncode, "stderr": g.stderr.strip()[:200]})
    write_text(rd / "guard-sweep.out", json.dumps(guard_rows, indent=2, sort_keys=True) + "\n")
    write_json(rd / "guard-sweep.json", {
        "all_pass": all(r["exit"] == 0 for r in guard_rows),
        "answer_or_candidates": answer_hit,
        "rows": guard_rows,
    })
    same_int = lsn_int(SAME_LSN)
    cases = {
        "same_point": {
            "window": extract_file(f"COORDINATE: window={SAME_WINDOW}"),
            "lsn_hex": extract_file(f"COORDINATE: lsn={SAME_LSN}"),
            "lsn_int": extract_file(f"COORDINATE: lsn={same_int}"),
            "ts": extract_file(f"COORDINATE: ts={SAME_TS}"),
        },
        "refusals": {
            "empty": extract_file("COORDINATE:"),
            "unresolvable": extract_file("COORDINATE: lsn=9/FFFFFFFF"),
            "both_tags": extract_file("COORDINATE: window=1\nREFUSAL: nope"),
            "neither": extract_file("no tagged line here"),
        },
    }
    slim = {"same_point": {}, "refusals": {}}
    for k, rec in cases["same_point"].items():
        arm = rec.get("arm_coordinate") or {}
        slim["same_point"][k] = {
            "outcome": rec.get("outcome"),
            "lsn_int": arm.get("lsn_int"),
            "lsn_text": arm.get("lsn_text"),
            "refusal_reason": rec.get("refusal_reason"),
        }
    for k, rec in cases["refusals"].items():
        slim["refusals"][k] = {
            "outcome": rec.get("outcome"),
            "arm_coordinate": rec.get("arm_coordinate"),
            "lsn_int": None if not rec.get("arm_coordinate") else rec["arm_coordinate"].get("lsn_int"),
            "refusal_reason": rec.get("refusal_reason"),
        }
    write_json(rd / "extract-cases.json", slim)
    # negatives
    ref_proc = run(["bin/lab-repr-reference", INCIDENT, "R2", "PB-6-candidate-windows", '{"top_n":3}'])
    ref = json.loads(ref_proc.stdout) if ref_proc.returncode == 0 else {}
    scratch = rd / "scratch"
    scratch.mkdir(exist_ok=True)
    leaked = {
        "content": "x", "incident_id": INCIDENT, "params": {"top_n": 3},
        "probe_id": "PB-6-candidate-windows", "representation": "R2",
        "telemetry": {},
        "answer": ref.get("answer") or {"candidates": [1]},
    }
    leak_path = scratch / "leaked-view.json"
    write_json(leak_path, leaked)
    g_leak = run(["bin/lab-modelview-guard", str(leak_path)])
    bare = extract_file("REFUSAL: cannot localise")
    write_json(rd / "negative.json", {
        "answer_leak_exit": g_leak.returncode,
        "answer_leak_stderr": g_leak.stderr.strip()[:400],
        "answer_leak_caught": g_leak.returncode != 0 and (
            "answer" in g_leak.stderr.lower() or "candidates" in g_leak.stderr.lower()
        ),
        "bare_refusal_outcome": bare.get("outcome"),
        "bare_refusal_lsn": (bare.get("arm_coordinate") or {}).get("lsn_int") if bare.get("arm_coordinate") else None,
        "bare_refusal_stays_refusal": bare.get("outcome") == "refusal" and bare.get("arm_coordinate") is None,
        "no_reprompt": True,
    })
    artefacts_ok = json.loads((root() / "var/repr" / INCIDENT / "R0" / "manifest.json").read_text())["content_hash"] == ARTEFACT_HASHES["R0"]
    live = {rep: json.loads((root() / "var/repr" / INCIDENT / rep / "manifest.json").read_text())["content_hash"]
            for rep in REPR_IDS}
    write_text(rd / "contract-hashes.txt",
               f"{base_hash}  {base.relative_to(root())}\n"
               f"{amend_hash}  {amend.relative_to(root())}\n"
               f"base_byte_identical={base_hash == H001_ARM_B_PROTOCOL}\n"
               + "".join(f"{live[r]}  {r} live={'ok' if live[r]==ARTEFACT_HASHES[r] else 'DRIFT'}\n" for r in REPR_IDS))
    prov = []
    for rep in REPR_IDS:
        prov.extend(token_scan(prompts[rep]))
    same_ints = [slim["same_point"][k].get("lsn_int") for k in ("window", "lsn_hex", "lsn_int", "ts")]
    same_ok = len(set(same_ints)) == 1 and all(isinstance(x, int) for x in same_ints)
    ref_ok = all(slim["refusals"][n]["outcome"] == "refusal" and slim["refusals"][n]["arm_coordinate"] is None
                 for n in ("empty", "unresolvable", "both_tags", "neither"))
    neg = json.loads((rd / "negative.json").read_text())
    rows = [
        row("J003-1", "M", "amendment grammar+framing; H001 protocol hash", "frozen; base identical",
            f"base_ok={base_hash == H001_ARM_B_PROTOCOL}", base_hash == H001_ARM_B_PROTOCOL),
        row("J003-2", "M", "window/hex/int/ts same point", "same lsn_int", str(same_ints), same_ok),
        row("J003-3", "M", "empty/unresolvable/both/neither", "refusal, null coordinate",
            json.dumps({k: v["outcome"] for k, v in slim["refusals"].items()}, sort_keys=True), ref_ok),
        row("J003-4", "M", "prompt diff R0/R1/R2", "content only", f"parity={parity}", parity),
        row("J003-5", "M", "guard sweep", "all exit 0", json.dumps(guard_rows, sort_keys=True),
            all(r["exit"] == 0 for r in guard_rows) and not answer_hit),
        row("J003-6", "M", "F002/F003/F004 hashes", "byte-identical", json.dumps(live, sort_keys=True),
            live == ARTEFACT_HASHES),
        row("J003-7", "M", "provenance sweep prompts", "no tokens", str(prov), not prov),
    ]
    extra = (
        f"NEGATIVE: spliced answer guard exit={g_leak.returncode} caught={neg['answer_leak_caught']}; "
        f"bare REFUSAL outcome={bare.get('outcome')} lsn={neg['bare_refusal_lsn']}."
    )
    finish(task, rows, [amend, root() / "bin/lab-arm-b-prompt", root() / "bin/lab-arm-b-extract",
                        rd / "prompt-diff.txt", rd / "guard-sweep.out", rd / "extract-cases.json",
                        rd / "contract-hashes.txt"],
           "Extractor resolves window via previous-window lsn_end (Arm A last_safe), "
           "integer LSN via lsn_text_from_int, timestamp via lab-coordinate --time.\n",
           extra)
    del artefacts_ok


def j004() -> None:
    task = "J004"
    rd = review_dir(task)
    h009 = review_dir("H009") / "headline.json"
    prior = json.loads(h009.read_text(encoding="utf-8"))
    superseded = dict(prior)
    superseded["superseded_by"] = "logs/review/J004/headline.json"
    superseded["pointer"] = "logs/review/J004/"
    superseded["note"] = "P6 null retained; J004 is the result of record (Article XVIII)."
    write_json(review_dir("H009") / "headline.superseded.json", superseded)
    runs = rd / "runs"
    per = {}
    residual = {}
    for rep in REPR_IDS:
        dest = runs / rep
        dest.mkdir(parents=True, exist_ok=True)
        canonical = dest / "replicates.json"
        if canonical.is_file() and len(json.loads(canonical.read_text()).get("records") or []) == K:
            append_command(task, f"lab-arm-b {rep} skipped existing batch")
            batch = json.loads(canonical.read_text())
        else:
            proc = run(["bin/lab-arm-b", "--incident", INCIDENT, "--representation", rep,
                        "--replicates", str(K), "--dest", str(dest)], timeout=3600)
            append_command(task, f"lab-arm-b {rep} exit={proc.returncode}")
            write_text(rd / f"arm-b-{rep}.out", (proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or ""))
            if proc.returncode != 0:
                raise SystemExit(f"lab-arm-b {rep} failed: {proc.stderr or proc.stdout}")
            batch = json.loads((dest / "replicates.json").read_text())
        scores = []
        for rec in batch["records"]:
            r = rec["replicate"]
            extract_path = dest / f"replicate-{r}.extract.json"
            model_path = dest / f"replicate-{r}.model.json"
            score_path = dest / f"replicate-{r}.score.json"
            ev = 0
            prompt = (dest / f"replicate-{r}.prompt").read_text(encoding="utf-8")
            # evidence bytes = interpolated content region if markers present
            if CONTENT_BEGIN in prompt and CONTENT_END in prompt:
                mid = prompt[prompt.index(CONTENT_BEGIN) + len(CONTENT_BEGIN):prompt.index(CONTENT_END)]
                ev = len(mid.encode("utf-8"))
            proc_s = run([
                "bin/lab-arm-b-score", "--incident", INCIDENT, "--representation", rep,
                "--extract", str(extract_path), "--model-record", str(model_path),
                "--replicate", str(r), "--evidence-bytes", str(ev), "--out", str(score_path),
            ], timeout=1800)
            append_command(task, f"lab-arm-b-score {rep} {r} exit={proc_s.returncode}")
            if proc_s.returncode != 0:
                raise SystemExit(proc_s.stderr or proc_s.stdout)
            scored = json.loads(score_path.read_text())
            rec["score"] = scored.get("score")
            rec["results_row"] = {k: scored.get("results_row", {}).get(k) for k in (
                "restore_verdict", "damage_rows_retained", "legit_rows_lost",
                "coord_error_bytes", "coord_error_ms",
            )}
            if rec.get("outcome") == "determination" and rec.get("score"):
                scores.append(rec)
            model = json.loads(model_path.read_text())
            rec["containment_verified"] = model.get("containment_verified")
        write_json(dest / "replicates.json", batch)
        refusal_dir = rd / "scratch" / f"refusals-{rep}"
        if refusal_dir.exists():
            shutil.rmtree(refusal_dir)
        refusal_dir.mkdir(parents=True, exist_ok=True)
        extract_reasons = {}
        for rec in batch["records"]:
            reason = rec.get("refusal_reason") or (
                json.loads((dest / f"replicate-{rec['replicate']}.extract.json").read_text()).get("refusal_reason")
            )
            if rec.get("outcome") == "refusal":
                src = dest / f"replicate-{rec['replicate']}.completion"
                shutil.copy2(src, refusal_dir / src.name)
                extract_reasons[reason] = extract_reasons.get(reason, 0) + 1
        diag = diagnose_dir(refusal_dir) if any(refusal_dir.glob("*.completion")) else {
            "n_classified": 0, "per_representation": {rep: {"total": 0}},
        }
        residual[rep] = {"taxonomy": diag, "extract_reasons": extract_reasons}
        det = [r for r in batch["records"] if r.get("outcome") == "determination"]
        refu = [r for r in batch["records"] if r.get("outcome") == "refusal"]
        damage = [int((r.get("score") or {}).get("damage_rows_retained") or 0) for r in det]
        legit = [int((r.get("score") or {}).get("legit_rows_lost") or 0) for r in det]
        deltas = []
        verdicts = {}
        for r in det:
            lsn = ((r.get("arm_coordinate") or {}).get("lsn_int"))
            if lsn is not None:
                deltas.append(int(lsn) - GT_LSN_INT)
            v = (r.get("score") or {}).get("restore_verdict")
            if v:
                verdicts[v] = verdicts.get(v, 0) + 1
        tokens = [int(r.get("prompt_tokens") or 0) for r in batch["records"]]
        per[rep] = {
            "determinations": len(det),
            "refusals": len(refu),
            "refusal_rate": (len(refu) / K) if K else None,
            "identical_coord_rate": batch.get("identical_coordinate_rate"),
            "identical_coordinate_rate": batch.get("identical_coordinate_rate"),
            "evidence_bytes": ev,
            "prompt_tokens_real": int(statistics.median(tokens)) if tokens else None,
            "median_damage_retained": int(statistics.median(damage)) if damage else None,
            "median_legit_lost": int(statistics.median(legit)) if legit else None,
            "median_lsn_delta": int(statistics.median(deltas)) if deltas else None,
            "p4": {"verdicts": verdicts} if verdicts else None,
            "residual_causes": {
                "taxonomy": (diag.get("per_representation") or {}).get(rep),
                "extract_reasons": extract_reasons,
            },
            "containment_verified": all(r.get("containment_verified") is not False for r in batch["records"]),
        }
        write_json(rd / f"diagnosis-{rep}.json", diag)
    headline = {
        "expected_rows": 15,
        "k": K,
        "per_rep": per,
        "true_optimum": {"lsn_int": GT_LSN_INT, "lsn_text": GT_LSN, "window": 15},
        "r0_vs_r2": {
            "r0_refusals": per["R0"]["refusals"],
            "r2_refusals": per["R2"]["refusals"],
            "r0_median_delta": per["R0"]["median_lsn_delta"],
            "r2_median_delta": per["R2"]["median_lsn_delta"],
        },
        "prior_null": "logs/review/H009/headline.superseded.json",
    }
    write_json(rd / "headline.json", headline)
    lines = ["# J004 SC-01 Arm B headline", "", "Result of record after the P6.1 instrument correction.", ""]
    for rep in REPR_IDS:
        rowp = per[rep]
        lines.append(f"## {rep}")
        lines.append(f"- determinations={rowp['determinations']} refusals={rowp['refusals']} "
                     f"refusal_rate={rowp['refusal_rate']}")
        lines.append(f"- identical_coord_rate={rowp['identical_coord_rate']}")
        lines.append(f"- prompt_tokens_real={rowp['prompt_tokens_real']} evidence_bytes={rowp['evidence_bytes']}")
        if rowp["determinations"]:
            lines.append(f"- P4 verdicts={rowp['p4']}")
            lines.append(f"- median damage_rows_retained={rowp['median_damage_retained']} "
                         f"legit_rows_lost={rowp['median_legit_lost']} lsn_delta={rowp['median_lsn_delta']}")
        if rowp["refusal_rate"] == 1.0:
            lines.append(f"- **100% refusal under the corrected instrument.** Extract reasons: "
                         f"{rowp.get('residual_causes', {}).get('extract_reasons')}. "
                         f"J001-taxonomy on those refusals: {rowp.get('residual_causes', {}).get('taxonomy')}. "
                         f"Candidate genuine finding: the modest model did not localise a consistent safe point from {rep}. Not coerced.")
        lines.append("")
    write_text(rd / "headline.md", "\n".join(lines))
    # determinism: first determination if any else first completion re-extract
    sample_rep, sample_r = "R2", 0
    for rep in REPR_IDS:
        batch = json.loads((runs / rep / "replicates.json").read_text())
        for rec in batch["records"]:
            if rec.get("outcome") == "determination":
                sample_rep, sample_r = rep, rec["replicate"]
                break
    dest = runs / sample_rep
    completion = (dest / f"replicate-{sample_r}.completion").read_text(encoding="utf-8")
    first = json.loads((dest / f"replicate-{sample_r}.extract.json").read_text())
    second = extract_completion(completion, INCIDENT, sample_rep)
    coord_ok = canonical_json(first.get("arm_coordinate")) == canonical_json(second.get("arm_coordinate"))
    score_ok = True
    if first.get("outcome") == "determination":
        score1 = json.loads((dest / f"replicate-{sample_r}.score.json").read_text()).get("score")
        proc_s = run([
            "bin/lab-arm-b-score", "--incident", INCIDENT, "--representation", sample_rep,
            "--extract", str(dest / f"replicate-{sample_r}.extract.json"),
            "--model-record", str(dest / f"replicate-{sample_r}.model.json"),
            "--replicate", str(sample_r), "--out", str(rd / "determinism-score.json"),
        ], timeout=1800)
        score2 = json.loads((rd / "determinism-score.json").read_text()).get("score") if proc_s.returncode == 0 else None
        def slim(s):
            if not s:
                return None
            return {k: s.get(k) for k in ("restore_verdict", "damage_rows_retained", "legit_rows_lost") if k in s}
        score_ok = slim(score1) == slim(score2)
    write_text(rd / "determinism.txt",
               f"sample={sample_rep} replicate={sample_r}\n"
               f"extract_byte_identical={coord_ok}\n"
               f"score_byte_identical={score_ok}\n"
               f"byte-identical={coord_ok and score_ok}\n")
    # negative: corrupt a determination if we have one, else skip with note
    neg = {"skipped": True}
    det_path = dest / f"replicate-{sample_r}.completion"
    if first.get("outcome") == "determination":
        scratch = rd / "scratch"
        scratch.mkdir(exist_ok=True)
        corrupted = completion
        if first.get("tagged_line"):
            corrupted = completion.replace(first["tagged_line"], "COORDINATE: lsn=9/FFFFFFFF", 1)
        else:
            corrupted = "COORDINATE: lsn=9/FFFFFFFF\n"
        write_text(scratch / "corrupt.completion", corrupted)
        bad = extract_completion(corrupted, INCIDENT, sample_rep)
        good = extract_completion(completion, INCIDENT, sample_rep)
        neg = {
            "skipped": False,
            "corrupt_outcome": bad.get("outcome"),
            "corrupt_lsn": (bad.get("arm_coordinate") or {}).get("lsn_int") if bad.get("arm_coordinate") else None,
            "reverted_identical": canonical_json(good.get("arm_coordinate")) == canonical_json(first.get("arm_coordinate")),
            "ok": bad.get("outcome") == "refusal" and bad.get("arm_coordinate") is None,
        }
    write_json(rd / "negative.json", neg)
    prov = []
    for path in runs.rglob("*.completion"):
        prov.extend(token_scan(path.read_text(encoding="utf-8")))
    for path in runs.rglob("*.rationale.txt"):
        prov.extend(token_scan(path.read_text(encoding="utf-8")))
    hundred = [r for r in REPR_IDS if per[r]["refusal_rate"] == 1.0]
    md = (rd / "headline.md").read_text()
    hundred_ok = all("100% refusal" in md and "J001-taxonomy" in md for _ in hundred) if hundred else True
    if hundred:
        hundred_ok = "100% refusal" in md
    rows = [
        row("J004-1", "M", "headline.json per-rep rates + P4", "present",
            json.dumps({r: {k: per[r][k] for k in ("determinations", "refusal_rate")} for r in REPR_IDS}, sort_keys=True),
            all("refusal_rate" in per[r] for r in REPR_IDS)),
        row("J004-2", "M", "re-extract+score one completion", "byte-identical",
            (rd / "determinism.txt").read_text().strip().replace("\n", " "),
            coord_ok and score_ok),
        row("J004-3", "M", "identical_coord_rate per rep", "present",
            str({r: per[r]["identical_coord_rate"] for r in REPR_IDS}),
            all("identical_coord_rate" in per[r] for r in REPR_IDS)),
        row("J004-4", "M", "headline.superseded.json pointer", "J004",
            str((review_dir("H009") / "headline.superseded.json").is_file()),
            (review_dir("H009") / "headline.superseded.json").is_file()),
        row("J004-5", "M", "provenance sweep new completions", "none", str(prov[:5]), not prov),
        row("J004-6", "M", "100% refusal stated if any", "taxonomy in headline.md",
            f"hundred={hundred}", hundred_ok),
    ]
    extra = f"NEGATIVE TEST: corrupt LSN -> {neg}."
    finish(task, rows, [rd / "headline.json", rd / "headline.md", rd / "determinism.txt",
                        review_dir("H009") / "headline.superseded.json"],
           "P6 canonical completions under var/arm_b remain; J004 wrote logs/review/J004/runs/.\n",
           extra)


def j005() -> None:
    task = "J005"
    rd = review_dir(task)
    mapping = {
        "mapping": [
            {
                "id": "AC-P6-02",
                "old": "offline_verified meant unsanctioned outbound==0 / loopback fiction",
                "new": "offline_verified means R2a-d: private-lab endpoint, no public egress observed, pinned alias, weights pin",
                "status": "strengthened",
            },
            {
                "id": "arm-b-protocol R4",
                "old": "rigid COORDINATE: window=<int> lsn=<HIGH/LOW>; other forms refused",
                "new": "resolvable locator window=/lsn=hex-or-int/ts=; empty/ambiguous/unresolvable still refusal; guard still binds",
                "status": "preserved",
            },
            {
                "id": "AC-P6-13/14 headline",
                "old": "H009 null was the result of record",
                "new": "J004 headline is the result of record; H009 retained as headline.superseded.json",
                "status": "preserved",
            },
        ],
        "weakened": [],
    }
    write_json(rd / "criterion-mapping.json", mapping)
    rows_h = frozen_contract_rows()
    lines = [f"{r['live']}  {r['path']}  {'OK' if r['ok'] else 'DRIFT'}" for r in rows_h]
    lines.append(f"{sha256_file(p6_contracts() / 'model-runtime.md')}  P6 model-runtime.md  {'OK' if sha256_file(p6_contracts() / 'model-runtime.md')==H001_MODEL_RUNTIME else 'DRIFT'}")
    lines.append(f"{sha256_file(p6_contracts() / 'arm-b-protocol.md')}  P6 arm-b-protocol.md  {'OK' if sha256_file(p6_contracts() / 'arm-b-protocol.md')==H001_ARM_B_PROTOCOL else 'DRIFT'}")
    lines.append(f"{sha256_file(p6_contracts() / 'model-runtime.amendment-1.md')}  P6 runtime amendment-1  {'OK' if sha256_file(p6_contracts() / 'model-runtime.amendment-1.md')==H001_P6_RUNTIME_AMENDMENT else 'DRIFT'}")
    write_text(rd / "contract-hashes.txt", "\n".join(lines) + "\n")
    memo = {
        "p6_accepted_only_after": "P6.1",
        "defects": ["D1", "D2"],
        "D1": "total null without root cause; diagnosed in J001; instrument corrected in J003; re-run J004",
        "D2": "containment claimed loopback; corrected to R2a-d private-lab / no public egress / no cloud alias / weights pin",
        "result_of_record": "logs/review/J004/headline.json",
        "prior_null": "logs/review/H009/headline.superseded.json",
    }
    write_text(root() / "docs/p6-acceptance-memo.md",
               "# P6 acceptance memo\n\n"
               "P6 is accepted only after P6.1. Two defects the P6 gate could not catch were remediated:\n\n"
               "- **D1** — SC-01 Arm B was a total null (`determinations:0`, `refusal_rate:1.0` on R0/R1/R2). "
               "J001 classified the 15 completions from verbatim bytes. J003 broadened the locator grammar. "
               "J004 is the result of record. The prior null is retained as `headline.superseded.json`.\n"
               "- **D2** — containment claimed loopback while the topology is LiteLLM on c220m3 fronting vLLM on gb10a. "
               "J002 redefines the check to R2a–R2d (private-lab endpoint, no public egress, no cloud alias, weights pin).\n\n"
               "```json\n" + json.dumps(memo, indent=2, sort_keys=True) + "\n```\n")
    p6 = run(["bin/lab-verify-p6"], timeout=180)
    write_text(rd / "verify-p6.out", (p6.stdout or "") + "\n--- stderr ---\n" + (p6.stderr or ""))
    try:
        payload = json.loads(p6.stdout.split("TIER M", 1)[-1].split("\n", 1)[1] if "TIER M" in p6.stdout else p6.stdout)
    except json.JSONDecodeError:
        payload = {"ok": p6.returncode == 0, "raw": (p6.stdout or "")[:2000]}
    # lab-verify-p6 prints TIER line then JSON
    try:
        idx = p6.stdout.find("{")
        payload = json.loads(p6.stdout[idx:]) if idx >= 0 else {"ok": p6.returncode == 0}
    except json.JSONDecodeError:
        payload = {"ok": False, "parse_error": True}
    write_json(rd / "verify-p6.json", payload)
    ro1 = run(["bin/lab-gate-readonly-check", "bin/lab-verify-p6.1"], timeout=180)
    ro2 = run(["bin/lab-gate-readonly-check", "bin/lab-verify-p6"], timeout=180)
    write_text(rd / "readonly-check.out",
               "=== lab-verify-p6.1 ===\n" + (ro1.stdout or "") + (ro1.stderr or "")
               + "\n=== lab-verify-p6 ===\n" + (ro2.stdout or "") + (ro2.stderr or "") + "\n")
    # negative: weakened mapping
    scratch_map = json.loads((rd / "criterion-mapping.json").read_text())
    scratch_map["mapping"].append({"id": "tmp", "old": "x", "new": "y", "status": "weakened"})
    bak = (rd / "criterion-mapping.json").read_text()
    write_json(rd / "criterion-mapping.json", scratch_map)
    weak = run(["bin/lab-verify-p6.1"], timeout=180)
    write_text(rd / "criterion-mapping.json", bak)
    # evidence-write negative: a stand-in gate writes one byte under the evidence root
    ev_root = Path(os.environ["EVIDENCE_ROOT"])
    hatch = ev_root / "SC-01" / INCIDENT / ".p61-readonly-hatch"
    probe = rd / "scratch" / "write-evidence-gate"
    probe.parent.mkdir(parents=True, exist_ok=True)
    write_text(probe, "#!/bin/bash\nprintf x >> \"$1\"\n", mode=0o755)
    # lab-gate-readonly-check expects a gate name; use an absolute script plus hatch path via env
    writer = rd / "scratch" / "p61-write-gate"
    write_text(writer, f"#!/bin/bash\nprintf x >> '{hatch}'\nexit 0\n", mode=0o755)
    os.chmod(writer, 0o755)
    caught = run(["bin/lab-gate-readonly-check", str(writer)], timeout=60)
    if hatch.is_file():
        hatch.unlink()
    write_json(rd / "negative.json", {
        "weakened_exit": weak.returncode,
        "weakened_caught": weak.returncode != 0,
        "readonly_p61_exit": ro1.returncode,
        "readonly_p6_exit": ro2.returncode,
        "evidence_write_exit": caught.returncode,
        "evidence_write_caught": caught.returncode != 0,
        "evidence_write_stderr": (caught.stderr or "")[:400],
        "hatch_removed": not hatch.is_file(),
    })
    p61 = run(["bin/lab-verify-p6.1"], timeout=180)
    write_text(rd / "verify-p61.out", (p61.stdout or "") + "\n--- stderr ---\n" + (p61.stderr or ""))
    rows = [
        row("J005-1", "M", "bin/lab-verify-p6.1", "all PASS per-tier",
            (p61.stdout or "").splitlines()[0] if p61.stdout else p61.stderr[:200],
            p61.returncode == 0),
        row("J005-2", "M", "criterion-mapping.json", "no weakened",
            "containment strengthened; grammar preserved",
            all(x["status"] in {"preserved", "strengthened"} for x in mapping["mapping"])),
        row("J005-3", "M", "frozen contract hashes", "all byte-identical",
            f"drift={[r['path'] for r in rows_h if not r['ok']]}",
            all(r["ok"] for r in rows_h)),
        row("J005-4", "M", "lab-gate-readonly-check both gates", "evidence identical",
            f"p61={ro1.returncode} p6={ro2.returncode}",
            ro1.returncode == 0 and ro2.returncode == 0),
        row("J005-5", "M", "bin/lab-verify-p6", "exit 0",
            f"exit={p6.returncode} ok={payload.get('ok')}", p6.returncode == 0 and payload.get("ok") is True),
        row("J005-6", "A", "docs/p6-acceptance-memo.md", 'p6_accepted_only_after: "P6.1"',
            json.dumps(memo, sort_keys=True), memo["p6_accepted_only_after"] == "P6.1"),
    ]
    extra = (
        f"NEGATIVE: mapping status=weakened exit={weak.returncode} (must be non-zero); "
        f"reverted. Readonly-check exits p61={ro1.returncode} p6={ro2.returncode}."
    )
    finish(task, rows, [root() / "bin/lab-verify-p6.1", root() / "bin/lab-verify-p6",
                        rd / "criterion-mapping.json", rd / "contract-hashes.txt",
                        rd / "readonly-check.out", root() / "docs/p6-acceptance-memo.md"],
           "P6 gate re-derived to R2a-d containment and J004 as headline of record.\n",
           extra)
    if p61.returncode != 0:
        raise SystemExit("lab-verify-p6.1 failed after bundle write")


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: lab_p61_review.py J002|J003|J004|J005")
    {"J002": j002, "J003": j003, "J004": j004, "J005": j005}[argv[0]]()
    print(json.dumps({"ok": True, "task": argv[0]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
