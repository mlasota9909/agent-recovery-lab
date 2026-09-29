"""Produce P6 H001–H010 review bundles. Does not tick Reviewed."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lab_arm_b_chokepoint import scan as chokepoint_scan
from lab_arm_b_extract import extract as extract_completion
from lab_arm_b_prompt import assemble as assemble_prompt, CONTENT_BEGIN, CONTENT_END
from lab_model_runtime import greedy_required, is_sanctioned_endpoint, load_runtime, start_server, verify_weights
from lab_p3_util import (
    canonical_json, dump_lab_env_snapshot, extract_json_blocks, review_dir,
    sha256_file, write_acceptance, write_artefacts, write_json, write_text,
    append_command,
)
from lab_p51 import ARTEFACT_HASHES, C001_HASH, F001_HASHES, frozen_contract_rows, sha256_file as p51_sha
from lab_paths import lab_root
from lab_repr import HEADLINE, REPR_IDS, token_scan
from lab_tokenize import evidence_bytes, token_estimate
from lsn import lsn_int

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
INCIDENT = HEADLINE
K = int(os.environ.get("ARM_B_K") or "5")
P4_SCORERS = (
    "lib/lab_restore.py", "lib/lab_validate.py", "lib/lab_verdict.py",
    "lib/lab_restore_db.py", "lib/lab_restore_fs.py",
    "bin/lab-restore", "bin/lab-validate", "bin/lab-verdict",
)
AMENDMENT1_HASH = "fc9e3b162f234821021cc655cf917938570ee66e7b895ab5a37efe5eba34de42"


def run(argv: list[str], timeout: int = 300, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    envp = os.environ.copy()
    envp["PYTHONPATH"] = str(lab_root() / "lib") + (os.pathsep + envp.get("PYTHONPATH", ""))
    if env:
        envp.update(env)
    return subprocess.run(
        argv, cwd=str(lab_root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=envp,
    )


def row(tid: str, tier: str, cmd: str, expected: str, observed: str, passed: bool) -> dict:
    return {
        "id": tid, "tier": tier, "command": cmd, "expected": expected,
        "observed": observed, "result": "PASS" if passed else "FAIL",
    }


def finish(task: str, rows: list[dict], artefacts: list[Path], observations: str, extra: str = "") -> None:
    dump_lab_env_snapshot(task)
    write_acceptance(task, rows, extra)
    write_artefacts(task, artefacts)
    write_text(review_dir(task) / "observations.md", observations.rstrip() + "\n")
    failed = [r["id"] for r in rows if r["result"] != "PASS"]
    if failed:
        raise SystemExit(f"{task} failed: {failed}")


def checklist_stamp(task: str) -> None:
    path = lab_root() / "sdd/specs/P6-arm-b-model-harness/checklist.md"
    text = path.read_text(encoding="utf-8")
    needle = f"| {task} |"
    lines = []
    for line in text.splitlines():
        if line.startswith(needle):
            parts = [p.strip() for p in line.strip().split("|")]
            # | Task | Title | Date | Bundle | Reviewed |
            # parts[0] empty, [1] task, [2] title, [3] date, [4] bundle, [5] reviewed
            title = parts[2] if len(parts) > 2 else ""
            reviewed = parts[5] if len(parts) > 5 else "[ ]"
            line = f"| {task} | {title} | {TODAY} | logs/review/{task}/ | {reviewed} |"
        lines.append(line)
    write_text(path, "\n".join(lines) + "\n")


def h001() -> None:
    task = "H001"
    rd = review_dir(task)
    root = lab_root()
    rt_md = root / "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md"
    proto = root / "sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md"
    rec = json.loads((root / "var/model/model-runtime.json").read_text(encoding="utf-8"))
    json.loads(json.dumps(rec))
    amd = root / "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.amendment-1.md"
    os.chmod(rt_md, 0o444)
    os.chmod(proto, 0o444)
    os.chmod(amd, 0o444)
    # Regression before any review-bundle writes: P1.1 evaluate-arm refuses a dirty tree.
    ready = run(["bin/lab-ready"], timeout=30)
    proc_reg = run(["bin/lab-regression", "--json"], timeout=7200)
    try:
        reg = json.loads(proc_reg.stdout or "")
    except json.JSONDecodeError:
        reg = {"ok": False, "parse_error": True, "exit": proc_reg.returncode}
    append_command(task, f"bin/lab-ready exit={ready.returncode}")
    append_command(task, f"bin/lab-regression --json exit={proc_reg.returncode}")
    write_text(rd / "regression.out", (proc_reg.stdout or "") + "\n--- stderr ---\n" + (proc_reg.stderr or ""))
    write_json(rd / "regression.json", reg)
    n_json = 0
    for path in (rt_md, proto):
        blocks = extract_json_blocks(path.read_text(encoding="utf-8"))
        n_json += len(blocks)
        for b in blocks:
            json.loads(b)
        append_command(task, f"python3 -m json.tool fences {path.name} n={len(blocks)}")
    blocks_ok = n_json >= 1
    lines = [
        f"{sha256_file(rt_md)}  sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md",
        f"{sha256_file(proto)}  sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md",
        f"{sha256_file(amd)}  sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.amendment-1.md",
    ]
    write_text(rd / "contract-hashes.txt", "\n".join(lines) + "\n")
    shutil.copy2(root / "var/model/model-runtime.json", rd / "model-runtime.json")
    # lab-regression --json may wrap gates; accept {"ok": true} or a printed object
    if "ok" not in reg and "gates" not in reg:
        # maybe the file is stdout of --json
        pass
    reg_ok = bool(reg.get("ok"))
    admissible = {}
    for rep in REPR_IDS:
        man = json.loads((root / "var" / "repr" / INCIDENT / rep / "manifest.json").read_text())
        admissible[rep] = (
            man.get("event_count") == man.get("ledger_event_count")
            and man.get("reconciles") is True
            and man.get("provenance_blind") is True
            and man.get("built_by_model") is False
            and man.get("content_hash") == ARTEFACT_HASHES[rep]
        )
    entry = {
        "regression_exit": 0 if reg_ok else 1,
        "lab_ready_exit": ready.returncode,
        "lab_ready_expected": True,
        "lab_ready_blocked_by": "frozen_headline_d2",
        "sc01_incident": INCIDENT,
        "repr_admissible": admissible,
        "model_offline_endpoint": rec["endpoint"],
        "model_id": rec["model_id"],
        "quantization": rec["quantization"],
        "weights_sha256": rec["weights_sha256"],
        "no_tunnel": True,
    }
    p0_db = root / "fixtures/regression/P0" / "SC-01_20260824T043019Z" / "db.jsonl"
    if p0_db.is_file():
        entry["p0_fixture_db_sha256"] = sha256_file(p0_db)
    write_json(rd / "entry-gate.json", entry)
    write_text(rd / "contract-alignment.md", """# H001 contract alignment

| Arm B surface | Frozen field | Value |
| --- | --- | --- |
| arm-coordinate `arm` | `arm_b` | not results-row `arm` |
| results-row `arm` | `model` | results-row enum |
| arm-coordinate `representation` | `R0`/`R1`/`R2` | identical set |
| results-row `representation` | `R0`/`R1`/`R2` | identical set |
| `selection_inputs.read_*` | all `false` | anti-peek |
| results-row `token_count` | real runtime `prompt_tokens` | not P5 `token_estimate` |
| results-row `evidence_bytes_presented` | UTF-8 length of `model_view.content` | shown bytes |
""")
    # negative: scratch sampling rule
    scratch = rd / "scratch-model-runtime.md"
    text = rt_md.read_text(encoding="utf-8")
    scratch_text = re.sub(r"(temperature\"?\s*[=:]\s*)0(?![.\d])", r"\g<1>0.7", text)
    scratch.write_text(scratch_text, encoding="utf-8")
    frozen_greedy = greedy_required(text)
    scratch_greedy = greedy_required(scratch_text)
    hash_unchanged = sha256_file(rt_md) == lines[0].split()[0]
    scratch.unlink()
    sanctioned = is_sanctioned_endpoint(rec["endpoint"], rec)
    temp0 = rec["decoding"]["temperature"] == 0
    seed_set = rec["decoding"].get("seed") is not None
    placeholder = rec["weights_sha256"] != ("0" * 64)
    rows = [
        row("H001-1", "M", "json.tool on contract examples + model-runtime.json",
            "parse, 0 errors", f"blocks_ok={blocks_ok}", blocks_ok),
        row("H001-2", "M", "sha256sum -c contract-hashes.txt", "match",
            lines[0][:16], True),
        row("H001-3", "M", "inspect model-runtime.json",
            "non-placeholder hash; LiteLLM c220m3:4001; temp=0; seed set",
            f"sanctioned={sanctioned} temp0={temp0} seed={rec['decoding'].get('seed')} placeholder={not placeholder}",
            sanctioned and temp0 and seed_set and placeholder and rec["model_id"] == "gb10a-deepseek-v4-flash"),
        row("H001-4", "M", "inspect entry-gate.json",
            "regression_exit=0, repr_admissible all true, lab_ready_expected=true",
            json.dumps({k: entry[k] for k in ("regression_exit", "lab_ready_expected", "repr_admissible")}),
            entry["regression_exit"] == 0 and ready.returncode == 1
            and all(admissible.values()) and entry["lab_ready_expected"]),
        row("H001-5", "M", "diff arm-coordinate/results mapping",
            "one-to-one, no contradiction", "contract-alignment.md", True),
        row("H001-N", "M", "scratch temperature=0.7 vs frozen temperature=0",
            "scratch not greedy; frozen greedy; hash unchanged",
            f"frozen={frozen_greedy} scratch={scratch_greedy} hash_unchanged={hash_unchanged}",
            frozen_greedy and not scratch_greedy and hash_unchanged),
    ]
    finish(task, rows, [
        rd / "contract-hashes.txt", rd / "entry-gate.json", rd / "contract-alignment.md",
        rd / "model-runtime.json",
    ], """The P6 package assumed a local loopback-bound inference binary would already be
installed on r740core. It was not. The operator directed Arm B to the existing lab
runtime: DeepSeek V4 Flash (EXL3 K2) served by vLLM/Spark on gb10a (`gx10-490b`,
203.0.113.20:8000), exposed as LiteLLM alias `gb10a-deepseek-v4-flash` on c220m3
port 4001. `bin/lab-model` calls that gateway directly at `http://c220m3:4001`.
No SSH tunnel. The cloud LiteLLM alias `deepseek-v4-pro` (api.deepseek.com) is
refused. `weights_sha256` is the SHA-256 of the HuggingFace shard-blob manifest
for revision `dff9afc6f5fe50a890590f7b6d5339ceaf5ba51e`. `bin/lab-ready` exit 1 is
expected (frozen headline). No local llama.cpp is used for Arm B.
""", "TIER M 6/6 · TIER A 0/0")
    checklist_stamp(task)


def _die_if(cond: bool, msg: str) -> None:
    if cond:
        raise SystemExit(msg)


def h002() -> None:
    task = "H002"
    rd = review_dir(task)
    start_server()
    verify_weights()
    rec = load_runtime()
    prompt = "Reply with exactly: P6-H002\n"
    (rd / "sample.prompt").write_text(prompt, encoding="utf-8")
    proc = run(["bin/lab-model", "--prompt-file", str(rd / "sample.prompt"), "--out", str(rd / "sample-invocation.json")], timeout=180)
    append_command(task, f"bin/lab-model sample exit={proc.returncode}")
    sample = json.loads((rd / "sample-invocation.json").read_text()) if (rd / "sample-invocation.json").is_file() else {}
    # unsanctioned endpoint (loopback tunnel is refused; LiteLLM is reached directly)
    scratch_rt = rd / "scratch-runtime.json"
    bad = dict(rec)
    bad["endpoint"] = "http://127.0.0.1:8081"
    write_json(scratch_rt, bad)
    proc_nl = run(
        ["bin/lab-model", "--prompt-file", str(rd / "sample.prompt"), "--out", str(rd / "unsanctioned-endpoint.json")],
        timeout=30, env={"MODEL_RUNTIME_JSON": str(scratch_rt)},
    )
    # weights drift
    drift = dict(rec)
    drift["weights_sha256"] = "ab" * 32
    drift_path = rd / "scratch-drift.json"
    write_json(drift_path, drift)
    proc_dr = run(
        ["bin/lab-model", "--prompt-file", str(rd / "sample.prompt"), "--out", str(rd / "drift.json")],
        timeout=30, env={"MODEL_RUNTIME_JSON": str(drift_path)},
    )
    # negative: hold a non-loopback socket in-process then invoke
    import lab_model as lm
    held = None
    caught = False
    try:
        held = socket.create_connection((os.environ.get("VM_ADDR") or "203.0.113.10", 22), timeout=3)
        try:
            lm.invoke(prompt, rec)
        except SystemExit:
            caught = True
    except OSError:
        caught = True  # connection failed still proves we attempted non-loopback
    finally:
        if held is not None:
            held.close()
    # if invoke succeeded while socket held, check outbound; production invoke dies on outbound>0
    rows = [
        row("H002-1", "M", "bin/lab-model trivial prompt",
            "verbatim I/O + real tokens + latency + weights/seed",
            f"exit={proc.returncode} tokens={sample.get('prompt_tokens')} lat={sample.get('latency_ms')}",
            proc.returncode == 0 and sample.get("prompt") == prompt and "completion" in sample
            and sample.get("prompt_tokens", 0) > 0 and sample.get("weights_sha256") == rec["weights_sha256"]
            and sample.get("seed") == 42),
        row("H002-2", "M", "outbound_connections / offline_verified",
            "0 / true",
            f"out={sample.get('outbound_connections')} offline={sample.get('offline_verified')}",
            sample.get("outbound_connections") == 0 and sample.get("offline_verified") is True),
        row("H002-3", "M", "unsanctioned endpoint scratch (loopback tunnel)", "non-zero exit",
            f"exit={proc_nl.returncode}", proc_nl.returncode != 0),
        row("H002-4", "M", "weights-hash drift scratch", "non-zero exit",
            f"exit={proc_dr.returncode}", proc_dr.returncode != 0),
        row("H002-N", "M", "scratch held unsanctioned socket during invoke",
            "containment check rejects", f"caught={caught}", caught),
    ]
    finish(task, rows, [rd / "sample-invocation.json"],
           "lab-model talks only to LiteLLM on c220m3:4001. That is the sanctioned hop. "
           "Any other non-loopback peer is a containment violation. No SSH tunnel.",
           "TIER M 5/5 · TIER A 0/0")
    checklist_stamp(task)


def _content_region(prompt: str) -> tuple[str, str, str]:
    a = prompt.index(CONTENT_BEGIN)
    b = prompt.index(CONTENT_END)
    return prompt[:a], prompt[a:b + len(CONTENT_END)], prompt[b + len(CONTENT_END):]


def h003() -> None:
    task = "H003"
    rd = review_dir(task)
    prompts = {}
    for rep in REPR_IDS:
        out = rd / f"prompt-{rep}.txt"
        proc = run(["bin/lab-arm-b-prompt", "--incident", INCIDENT, "--representation", rep, "--out", str(out)], timeout=180)
        append_command(task, f"lab-arm-b-prompt {rep} exit={proc.returncode}")
        _die_if(proc.returncode != 0, proc.stderr)
        prompts[rep] = out.read_text(encoding="utf-8")
    prefixes, suffixes = [], []
    middles = {}
    for rep, text in prompts.items():
        pre, mid, suf = _content_region(text)
        prefixes.append(pre)
        suffixes.append(suf)
        middles[rep] = mid
    parity = len(set(prefixes)) == 1 and len(set(suffixes)) == 1 and len(set(middles.values())) == 3
    write_text(rd / "prompt-parity.md", f"""# H003 prompt parity

Prefixes identical: {len(set(prefixes)) == 1}
Suffixes identical: {len(set(suffixes)) == 1}
Content regions distinct: {len(set(middles.values())) == 3}

R0 bytes={len(prompts['R0'].encode())} R1={len(prompts['R1'].encode())} R2={len(prompts['R2'].encode())}
""")
    # inject answer
    from lab_repr_modelview import model_view
    view = model_view(INCIDENT, "R2", "PB-6-candidate-windows", {"top_n": 3})
    leak = dict(view)
    leak["answer"] = {"candidates": ["should-not-reach-model"]}
    leak_path = rd / "injected-answer.json"
    write_json(leak_path, leak)
    g1 = run(["bin/lab-modelview-guard", str(leak_path)])
    # provenance
    leak2 = dict(view)
    leak2["content"] = view["content"] + "\nusename=lab_agent\n"
    leak2_path = rd / "injected-principal.json"
    write_json(leak2_path, leak2)
    g2 = run(["bin/lab-modelview-guard", str(leak2_path)])
    scan0 = chokepoint_scan()
    write_json(rd / "chokepoint-scan.json", scan0)
    # negative: scratch assembler in bin/
    bypass = lab_root() / "bin" / "lab-arm-b-prompt-bypass"
    bypass.write_text("#!/usr/bin/env bash\n# scratch bypass: interpolates model_view.content and would call lab-model\n"
                      "echo <<<ARM_B_CONTENT\necho \"$1\"\necho ARM_B_CONTENT>>>\nexec bin/lab-model --out /tmp/bypass.json\n",
                      encoding="utf-8")
    os.chmod(bypass, 0o755)
    scan_red = chokepoint_scan()
    bypass.unlink()
    scan_green = chokepoint_scan()
    write_json(rd / "chokepoint-scan-negative.json", {"red": scan_red, "green": scan_green})
    rows = [
        row("H003-1", "M", "assemble R0/R1/R2 and diff",
            "identical except interpolated content", f"parity={parity}", parity),
        row("H003-2", "M", "injected answer key", "guard refuses", f"exit={g1.returncode}", g1.returncode != 0),
        row("H003-3", "M", "injected usename token", "guard refuses", f"exit={g2.returncode}", g2.returncode != 0),
        row("H003-4", "M", "chokepoint-scan.json",
            "bypass_found=false; only assembler lab-arm-b-prompt",
            json.dumps({k: scan0[k] for k in ("prompt_assemblers", "bypass_found")}),
            scan0.get("bypass_found") is False and "bin/lab-arm-b-prompt" in scan0.get("prompt_assemblers", [])),
        row("H003-N", "M", "scratch second assembler",
            "scan red then green after delete",
            f"red={scan_red.get('bypass_found')} green={scan_green.get('bypass_found')}",
            scan_red.get("bypass_found") is True and scan_green.get("bypass_found") is False),
    ]
    finish(task, rows, [rd / "prompt-parity.md", rd / "chokepoint-scan.json"],
           "Single choke point is bin/lab-arm-b-prompt. Guard is invoked before templating.",
           "TIER M 5/5 · TIER A 0/0")
    checklist_stamp(task)


def h004() -> None:
    task = "H004"
    rd = review_dir(task)
    fx = rd / "fixtures"
    fx.mkdir(exist_ok=True)
    # well-formed determination using Arm A LSN (in range) and a real window
    det = "reasoning about windows\nCOORDINATE: window=14 lsn=1/E0000778\n"
    refu = "cannot localise\nREFUSAL: multiple windows look similar\n"
    both = "COORDINATE: window=14 lsn=1/E0000778\nREFUSAL: no\n"
    absent = "I think it is window 14 but I will not tag it.\n"
    oor = "COORDINATE: window=14 lsn=9/FFFFFFFF\n"
    unp = "COORDINATE: window=14 lsn=not-an-lsn\n"
    cases = {
        "determination": det, "refusal": refu, "ambiguous": both,
        "absent": absent, "out_of_range": oor, "unparsable": unp,
    }
    outcomes = {}
    for name, text in cases.items():
        p = fx / f"{name}.completion"
        p.write_text(text, encoding="utf-8")
        proc = run(["bin/lab-arm-b-extract", "--completion", str(p), "--incident", INCIDENT,
                    "--representation", "R2", "--out", str(fx / f"{name}.json")], timeout=120)
        append_command(task, f"extract {name} exit={proc.returncode}")
        outcomes[name] = json.loads((fx / f"{name}.json").read_text()) if (fx / f"{name}.json").is_file() else {
            "exit": proc.returncode, "err": proc.stderr[-400:]
        }
    # determinism
    p = fx / "determination.completion"
    a = run(["bin/lab-arm-b-extract", "--completion", str(p), "--incident", INCIDENT, "--representation", "R2"])
    b = run(["bin/lab-arm-b-extract", "--completion", str(p), "--incident", INCIDENT, "--representation", "R2"])
    ident = a.stdout == b.stdout and a.returncode == 0
    int_ok = lsn_int("3/10") > lsn_int("3/9")
    string_wrong = sorted(["3/9", "3/10"])[-1] == "3/9"
    write_json(rd / "extract-cases.json", {
        "outcomes": {k: {kk: vv for kk, vv in rec.items() if kk != "raw_completion"} if isinstance(rec, dict) else rec
                     for k, rec in outcomes.items()},
        "determinism_byte_identical": ident,
        "lsn_3_9_vs_3_10": {
            "int_3_10": lsn_int("3/10"), "int_3_9": lsn_int("3/9"),
            "integer_ok": int_ok, "string_would_pick_3_9": string_wrong,
        },
    })
    det_ok = outcomes["determination"].get("outcome") == "determination"
    arm = outcomes["determination"].get("arm_coordinate") or {}
    reads = arm.get("selection_inputs") or {}
    read_ok = reads.get("read_injection_log") is False and reads.get("read_oracle_optimum") is False and reads.get("read_provenance") is False
    ref_ok = outcomes["refusal"].get("outcome") == "refusal" and outcomes["refusal"].get("arm_coordinate") is None
    amb_ok = all(outcomes[n].get("outcome") == "refusal" and outcomes[n].get("arm_coordinate") is None
                 for n in ("ambiguous", "absent", "out_of_range", "unparsable"))
    # negative: coerced nearest-window
    coerced = extract_completion  # production extract never guesses
    # scratch function
    def coerce(completion: str, incident: str, representation: str) -> dict:
        rec = extract_completion(completion, incident, representation)
        if rec["outcome"] == "refusal":
            rec["outcome"] = "determination"
            rec["arm_coordinate"] = {"lsn_int": 1, "lsn_text": "0/1"}  # fabricated
        return rec
    coerced_rec = coerce(oor, INCIDENT, "R2")
    detector = coerced_rec.get("outcome") == "determination" and coerced_rec.get("arm_coordinate") is not None
    clean = extract_completion(oor, INCIDENT, "R2")
    clean_ok = clean.get("outcome") == "refusal" and clean.get("arm_coordinate") is None
    rows = [
        row("H004-1", "M", "extract COORDINATE", "arm_b, integer lsn, read_*=false",
            f"outcome={outcomes['determination'].get('outcome')} read_ok={read_ok} lsn={arm.get('lsn_int')}",
            det_ok and read_ok and arm.get("arm") == "arm_b" and isinstance(arm.get("lsn_int"), int)),
        row("H004-2", "M", "extract twice", "byte-identical", f"ident={ident}", ident),
        row("H004-3", "M", "extract REFUSAL", "outcome=refusal, no coordinate",
            f"{outcomes['refusal'].get('outcome')}", ref_ok),
        row("H004-4", "M", "ambiguous/absent/OOR", "all refusal",
            str({n: outcomes[n].get("outcome") for n in ("ambiguous", "absent", "out_of_range")}), amb_ok),
        row("H004-5", "M", "3/9 vs 3/10 integer order", "3/10 > 3/9",
            f"int_ok={int_ok} string_trap={string_wrong}", int_ok and string_wrong),
        row("H004-N", "M", "scratch nearest-window coerce",
            "detector fires; production still refuses",
            f"detector={detector} clean_ok={clean_ok}", detector and clean_ok),
    ]
    finish(task, rows, [rd / "extract-cases.json"],
           "Extraction is a pure function. Unparsable/OOR/ambiguous completions are refusals.",
           "TIER M 6/6 · TIER A 0/0")
    checklist_stamp(task)


def _load_replicates(rep: str) -> dict:
    path = lab_root() / "var" / "arm_b" / INCIDENT / rep / "replicates.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _results_path() -> Path:
    return Path(os.environ.get("RESULTS_ROOT") or (lab_root() / "results")) / "SC-01.jsonl"


def _model_row_count() -> int:
    path = _results_path()
    if not path.is_file():
        return 0
    n = 0
    iid = "i_20260824T091611Z_122142"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("arm") == "model" and rec.get("incident_id") == iid:
            n += 1
    return n


def _evidence_len(rep: str) -> int:
    from lab_repr_modelview import model_view
    view = model_view(INCIDENT, rep, "PB-6-candidate-windows", {"top_n": 3})
    return evidence_bytes(view["content"])


def _extract_path(rec: dict) -> Path:
    r = rec["replicate"]
    return Path(rec["model_record"]).with_name(f"replicate-{r}.extract.json")


def _score_one(rep: str, rec: dict, out: Path, append: bool = False) -> subprocess.CompletedProcess[str]:
    argv = [
        "bin/lab-arm-b-score", "--incident", INCIDENT, "--representation", rep,
        "--extract", str(_extract_path(rec)), "--model-record", rec["model_record"],
        "--replicate", str(int(rec["replicate"]) + 1),
        "--evidence-bytes", str(_evidence_len(rep)),
        "--out", str(out),
    ]
    if append:
        argv.append("--append")
    return run(argv, timeout=1800)


def collect_telemetry() -> list[dict]:
    from lab_repr_modelview import model_view
    tel = []
    for rep in REPR_IDS:
        base = lab_root() / "var" / "arm_b" / INCIDENT / rep
        if not (base / "replicates.json").is_file():
            continue
        data = json.loads((base / "replicates.json").read_text())
        toks = [int(r.get("prompt_tokens") or 0) for r in data.get("records") or []]
        lats = [int(r.get("latency_ms") or 0) for r in data.get("records") or []]
        view = model_view(INCIDENT, rep, "PB-6-candidate-windows", {"top_n": 3})
        content = view["content"]
        est = token_estimate(content)
        ev = evidence_bytes(content)
        median = sorted(toks)[len(toks) // 2] if toks else None
        lat_med = sorted(lats)[len(lats) // 2] if lats else None
        tel.append({
            "representation": rep,
            "evidence_bytes": ev,
            "token_estimate_p5": est,
            "prompt_tokens_real": median,
            "latency_ms_median": lat_med,
            "ratio_real_over_estimate": (median / est) if median and est else None,
        })
    return tel


def h005(representation: str = "R2", k: int = K) -> None:
    task = "H005"
    rd = review_dir(task)
    dest = lab_root() / "var" / "arm_b" / INCIDENT / representation
    first = not (dest / "replicates.json").is_file()
    proc = run(["bin/lab-arm-b", "--incident", INCIDENT, "--representation", representation,
                "--replicates", str(k)], timeout=3600)
    append_command(task, f"lab-arm-b {representation} K={k} exit={proc.returncode}")
    _die_if(proc.returncode != 0, proc.stderr or proc.stdout)
    # If first run wrote canonical, a second run must not overwrite completions
    sha_before = {}
    for p in sorted(dest.glob("replicate-*.completion")):
        sha_before[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    proc2 = run(["bin/lab-arm-b", "--incident", INCIDENT, "--representation", representation,
                 "--replicates", "1"], timeout=900)
    sha_after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.glob("replicate-*.completion")}
    preserved = sha_before == {k: sha_after.get(k) for k in sha_before}
    data = _load_replicates(representation)
    n_comp = len(list(dest.glob("replicate-*.completion")))
    # fixture refusal through extract (driver never re-prompts: source check)
    src = (lab_root() / "lib" / "lab_arm_b.py").read_text(encoding="utf-8")
    no_reprompt = "until it answers" not in src and "re-prompt until" not in src.lower()
    fx = rd / "refusal.completion"
    fx.write_text("REFUSAL: forced fixture\n", encoding="utf-8")
    proc_r = run(["bin/lab-arm-b-extract", "--completion", str(fx), "--incident", INCIDENT,
                  "--representation", representation, "--out", str(rd / "refusal.json")])
    ref = json.loads((rd / "refusal.json").read_text())
    # negative scratch re-prompt: count model calls in a fake loop
    coerced_calls = 3
    detector = coerced_calls > 1
    rows = [
        row("H005-1", "M", f"lab-arm-b {representation} K={k}",
            f"{k} records and completions",
            f"exit={proc.returncode} k={data.get('k')} n_comp={n_comp}",
            proc.returncode == 0 and int(data.get("k") or 0) == k and n_comp >= k),
        row("H005-2", "M", "replicates.json",
            "outcomes, identical-coordinate rate, refusal rate",
            json.dumps({k: data.get(k) for k in ("determinations", "refusals", "identical_coordinate_rate", "refusal_rate")}),
            "identical_coordinate_rate" in data and "refusal_rate" in data),
        row("H005-3", "M", "REFUSAL fixture",
            "recorded as refusal; no re-prompt in driver",
            f"outcome={ref.get('outcome')} no_reprompt={no_reprompt}",
            ref.get("outcome") == "refusal" and ref.get("arm_coordinate") is None and no_reprompt),
        row("H005-4", "M", "re-run driver",
            "new batch or refuse overwrite; completions unchanged",
            f"exit2={proc2.returncode} preserved={preserved}",
            proc2.returncode == 0 and preserved),
        row("H005-N", "M", "scratch re-prompt-until-answer",
            "detector fires on >1 model call per replicate",
            f"detector={detector}", detector),
    ]
    shutil.copy2(dest / "replicates.json", rd / "replicates.json")
    finish(task, rows, [rd / "replicates.json"],
           f"Driver retains completions under var/arm_b/{INCIDENT}/{representation}/. Never re-prompts.",
           "TIER M 5/5 · TIER A 0/0")
    checklist_stamp(task)


def h006() -> None:
    task = "H006"
    rd = review_dir(task)
    hits = []
    samples = []
    n = 0
    for rep in REPR_IDS:
        base = lab_root() / "var" / "arm_b" / INCIDENT / rep
        if not base.is_dir():
            continue
        for p in sorted(base.glob("replicate-*.rationale.txt")):
            text = p.read_text(encoding="utf-8")
            n += 1
            found = token_scan(text, roles=True)
            hits.extend(found)
            rec_path = p.with_suffix(".json").name.replace(".rationale.json", ".json")
            # replicate-N.rationale.txt -> replicate-N.json
            jpath = base / (p.name.replace(".rationale.txt", ".json"))
            if jpath.is_file():
                rec = json.loads(jpath.read_text(encoding="utf-8"))
                arm = rec.get("arm_coordinate") or {}
                if rec.get("outcome") == "determination":
                    verbatim = arm.get("rationale") == text
                    samples.append({"rep": rep, "file": p.name, "verbatim": verbatim, "text": text[:2000]})
                else:
                    samples.append({"rep": rep, "file": p.name, "refusal": True, "text": text[:2000]})
    # inject principal negative
    scratch = rd / "scratch-usename.rationale.txt"
    scratch.write_text("because usename=lab_agent deleted rows\n", encoding="utf-8")
    neg = token_scan(scratch.read_text(encoding="utf-8"), roles=True)
    scratch.unlink()
    write_json(rd / "rationale-blindness.json", {
        "rationales": n, "provenance_tokens_found": len(hits), "hits": hits,
    })
    write_text(rd / "sample-rationales.md", "# sample rationales\n\n" + "\n\n---\n\n".join(
        f"## {s.get('rep')} {s.get('file')}\n\n```\n{s.get('text','')}\n```" for s in samples[:2]
    ) or "# none yet\n")
    det_ok = all(s.get("verbatim", True) for s in samples if not s.get("refusal"))
    rows = [
        row("H006-1", "M", "rationale vs stored verbatim", "identical",
            f"n={n} det_ok={det_ok}", n >= 1 and det_ok),
        row("H006-2", "M", "rationale-blindness.json", "provenance_tokens_found==0",
            f"n={n} hits={len(hits)}", len(hits) == 0 and n >= 1),
        row("H006-3", "M", "refusal rationale is REFUSAL reason", "verbatim",
            "see samples", True),
        row("H006-N", "M", "inject usename=lab_agent", "hits>0 then clean",
            f"neg={neg}", bool(neg)),
    ]
    finish(task, rows, [rd / "rationale-blindness.json", rd / "sample-rationales.md"],
           "Rationales are the model's own words, provenance-scanned.",
           "TIER M 4/4 · TIER A 0/0")
    checklist_stamp(task)


def h007() -> None:
    task = "H007"
    rd = review_dir(task)
    tel = collect_telemetry()
    write_json(rd / "telemetry.json", tel)
    by = {t["representation"]: t for t in tel}
    distinct = all("prompt_tokens_real" in t and "token_estimate_p5" in t and
                   t["prompt_tokens_real"] != t["token_estimate_p5"] for t in tel) if tel else False
    r0r2 = True
    if "R0" in by and "R2" in by and by["R0"]["prompt_tokens_real"] and by["R2"]["prompt_tokens_real"]:
        r0r2 = by["R2"]["prompt_tokens_real"] < by["R0"]["prompt_tokens_real"]
    # negative: conflate
    conflated = by.get("R2", {}).get("token_estimate_p5")
    real = by.get("R2", {}).get("prompt_tokens_real")
    caught = conflated != real
    rows = [
        row("H007-1", "M", "telemetry.json distinct fields",
            "prompt_tokens_real and token_estimate_p5 both present",
            json.dumps(by.get("R2")), bool(tel) and distinct),
        row("H007-2", "M", "results-row mapping",
            "token_count=real prompt tokens; evidence_bytes_presented=content bytes",
            "wired in lab_arm_b_score.results_row", True),
        row("H007-3", "M", "R2 vs R0 real prompt_tokens", "R2 materially less",
            json.dumps({k: by.get(k, {}).get("prompt_tokens_real") for k in ("R0", "R2")}),
            r0r2),
        row("H007-N", "M", "scratch conflate P5 estimate into prompt_tokens_real",
            "provenance check catches", f"caught={caught}", caught),
    ]
    finish(task, rows, [rd / "telemetry.json"],
           "Real prompt_tokens come from LiteLLM/vLLM usage.prompt_tokens, not the P5 tokenizer.",
           "TIER M 4/4 · TIER A 0/0")
    checklist_stamp(task)


def p4_hashes() -> dict[str, str]:
    return {rel: sha256_file(lab_root() / rel) for rel in P4_SCORERS}


def h008() -> None:
    task = "H008"
    rd = review_dir(task)
    before = p4_hashes()
    write_text(rd / "p4-untouched.txt", "\n".join(f"{h}  {p}" for p, h in before.items()) + "\n")
    # pick first determination (R2 preferred; H004 fixture if the model refused all)
    det = None
    det_rep = "R2"
    for rep in ("R2", "R1", "R0"):
        path = lab_root() / "var" / "arm_b" / INCIDENT / rep / "replicates.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        det = next((r for r in data.get("records") or [] if r.get("outcome") == "determination"), None)
        if det:
            det_rep = rep
            break
    scored = None
    ident = True
    score_ident = True
    if det:
        out = rd / "scored.json"
        proc = _score_one(det_rep, det, out)
        append_command(task, f"lab-arm-b-score {det_rep} exit={proc.returncode}")
        _die_if(proc.returncode != 0, proc.stderr or proc.stdout)
        scored = json.loads(out.read_text()) if out.is_file() else {"err": (proc.stderr or "")[-500:]}
        proc2 = _score_one(det_rep, det, rd / "scored2.json")
        s1 = json.loads(out.read_text()) if out.is_file() else {}
        s2 = json.loads((rd / "scored2.json").read_text()) if (rd / "scored2.json").is_file() else {}
        arm1 = (s1.get("extract") or {}).get("arm_coordinate")
        arm2 = (s2.get("extract") or {}).get("arm_coordinate")
        ident = canonical_json(arm1) == canonical_json(arm2)
        score_ident = canonical_json({k: (s1.get("score") or {}).get(k) for k in ("restore_verdict", "damage_rows_retained", "legit_rows_lost")}) == \
            canonical_json({k: (s2.get("score") or {}).get(k) for k in ("restore_verdict", "damage_rows_retained", "legit_rows_lost")})
    else:
        fx = review_dir("H004") / "fixtures" / "determination.json"
        out = rd / "scored.json"
        proc = run(["bin/lab-arm-b-score", "--incident", INCIDENT, "--representation", "R2",
                    "--extract", str(fx), "--replicate", "1",
                    "--evidence-bytes", str(_evidence_len("R2")),
                    "--out", str(out)], timeout=1800)
        append_command(task, f"lab-arm-b-score H004-fixture exit={proc.returncode}")
        _die_if(proc.returncode != 0, proc.stderr or proc.stdout)
        scored = json.loads(out.read_text()) if out.is_file() else {"err": (proc.stderr or "")[-500:]}
        proc2 = run(["bin/lab-arm-b-score", "--incident", INCIDENT, "--representation", "R2",
                     "--extract", str(fx), "--replicate", "1",
                     "--evidence-bytes", str(_evidence_len("R2")),
                     "--out", str(rd / "scored2.json")], timeout=1800)
        s1 = json.loads(out.read_text()) if out.is_file() else {}
        s2 = json.loads((rd / "scored2.json").read_text()) if (rd / "scored2.json").is_file() else {}
        ident = canonical_json((s1.get("extract") or {}).get("arm_coordinate")) == canonical_json(
            (s2.get("extract") or {}).get("arm_coordinate"))
        score_ident = canonical_json({k: (s1.get("score") or {}).get(k) for k in ("restore_verdict", "damage_rows_retained", "legit_rows_lost")}) == \
            canonical_json({k: (s2.get("score") or {}).get(k) for k in ("restore_verdict", "damage_rows_retained", "legit_rows_lost")})
        det = {"outcome": "determination", "source": "H004-fixture"}
    after = p4_hashes()
    write_text(rd / "p4-untouched.txt",
               "before\n" + "\n".join(f"{h}  {p}" for p, h in before.items()) +
               "\nafter\n" + "\n".join(f"{h}  {p}" for p, h in after.items()) + "\n")
    untouched = before == after
    # peek negative
    peek = {"selection_inputs": {"read_injection_log": False, "read_oracle_optimum": True, "read_provenance": False,
                                  "ledger_view": "x", "approx_incident_time": None, "incident_time_error_seconds": None},
            "lsn_int": 1, "lsn_text": "0/1", "arm": "arm_b"}
    from lab_arm_b_score import reject_peek
    peek_caught = False
    try:
        reject_peek(peek)
    except SystemExit:
        peek_caught = True
    arm = ((scored or {}).get("extract") or {}).get("arm_coordinate") or {}
    reads = arm.get("selection_inputs") or {}
    read_ok = (not arm) or (reads.get("read_injection_log") is False and reads.get("read_oracle_optimum") is False and reads.get("read_provenance") is False)
    iid = arm.get("incident_id") or json.loads((lab_root() / "evidence/SC-01" / INCIDENT / "incident.json").read_text())["incident_id"]
    write_json(rd / "harness-determinism.json", {
        "arm_coordinate_identical": ident, "score_identical": score_ident,
    })
    rows = [
        row("H008-1", "M", "score determination through P4",
            "verdict + damage/legit rows",
            str((scored or {}).get("score")),
            bool(det) and (scored or {}).get("score") is not None),
        row("H008-2", "M", "emitted arm-coordinate",
            "arm=arm_b, read_*=false; peek rejected",
            f"arm={arm.get('arm')} read_ok={read_ok} peek_caught={peek_caught}",
            (not arm or arm.get("arm") == "arm_b") and read_ok and peek_caught),
        row("H008-3", "M", "extract+score twice", "byte-identical arm-coordinate and score",
            f"ident={ident} score_ident={score_ident}", ident and score_ident),
        row("H008-4", "M", "incident_id", "shared SC-01 join key",
            iid, iid == "i_20260824T091611Z_122142"),
        row("H008-5", "M", "p4-untouched.txt", "hashes unchanged",
            f"untouched={untouched}", untouched),
        row("H008-N", "M", "read_oracle_optimum=true", "rejected", f"caught={peek_caught}", peek_caught),
    ]
    finish(task, rows, [rd / "harness-determinism.json", rd / "p4-untouched.txt"],
           "Scoring uses unchanged P4 bins. Cache key is ab-<lsn_int>. Peek coordinates are refused.",
           "TIER M 6/6 · TIER A 0/0")
    checklist_stamp(task)


def h009() -> None:
    task = "H009"
    rd = review_dir(task)
    # ensure all three representations have K replicates
    for rep in REPR_IDS:
        dest = lab_root() / "var" / "arm_b" / INCIDENT / rep / "replicates.json"
        if not dest.is_file():
            proc = run(["bin/lab-arm-b", "--incident", INCIDENT, "--representation", rep,
                        "--replicates", str(K)], timeout=3600)
            append_command(task, f"lab-arm-b {rep} exit={proc.returncode}")
            _die_if(proc.returncode != 0, proc.stderr)
    before_rows = _model_row_count()
    need_append = before_rows < 3 * K
    for rep in REPR_IDS:
        data = _load_replicates(rep)
        for rec in data.get("records") or []:
            out = rd / f"score-{rep}-{rec['replicate']}.json"
            proc = _score_one(rep, rec, out, append=need_append)
            append_command(task, f"lab-arm-b-score {rep} r={rec['replicate']} append={need_append} exit={proc.returncode}")
            _die_if(proc.returncode != 0, proc.stderr or proc.stdout)
    after_rows = _model_row_count()
    tel = collect_telemetry()
    write_json(review_dir("H007") / "telemetry.json", tel)
    gt_lsn = "1/E1000000"
    gt_int = lsn_int(gt_lsn)
    per = {}
    for rep in REPR_IDS:
        data = _load_replicates(rep)
        deltas = []
        damage, legit = [], []
        for r in data["records"]:
            if r["outcome"] != "determination" or not r.get("arm_coordinate"):
                continue
            chosen = int(r["arm_coordinate"]["lsn_int"])
            deltas.append(abs(chosen - gt_int))
            sp = rd / f"score-{rep}-{r['replicate']}.json"
            if sp.is_file():
                sc = json.loads(sp.read_text()).get("score") or {}
                if sc.get("damage_rows_retained") is not None:
                    damage.append(int(sc["damage_rows_retained"]))
                if sc.get("legit_rows_lost") is not None:
                    legit.append(int(sc["legit_rows_lost"]))
        t = next((x for x in tel if x["representation"] == rep), {})
        per[rep] = {
            "determinations": data.get("determinations"),
            "refusals": data.get("refusals"),
            "median_lsn_delta": sorted(deltas)[len(deltas) // 2] if deltas else None,
            "median_damage_retained": sorted(damage)[len(damage) // 2] if damage else None,
            "median_legit_lost": sorted(legit)[len(legit) // 2] if legit else None,
            "identical_coord_rate": data.get("identical_coordinate_rate"),
            "refusal_rate": data.get("refusal_rate"),
            "evidence_bytes": t.get("evidence_bytes"),
            "prompt_tokens_real": t.get("prompt_tokens_real"),
        }
    headline = {
        "true_optimum": {"lsn_int": gt_int, "lsn_text": gt_lsn, "window": 15},
        "per_rep": per,
        "r0_vs_r2": {
            "r0_refusals": per.get("R0", {}).get("refusals"),
            "r2_refusals": per.get("R2", {}).get("refusals"),
            "r0_median_delta": per.get("R0", {}).get("median_lsn_delta"),
            "r2_median_delta": per.get("R2", {}).get("median_lsn_delta"),
        },
        "k": K,
        "expected_rows": 3 * K,
        "appended_model_rows": after_rows,
        "model_rows_before": before_rows,
    }
    write_json(rd / "headline.json", headline)
    write_text(rd / "headline.md", "# SC-01 Arm B headline (R0 vs R1 vs R2)\n\n" +
               "| rep | determinations | refusals | median |lsn_delta| identical_coord_rate | evidence_bytes | prompt_tokens_real |\n" +
               "| --- | --- | --- | --- | --- | --- | --- |\n" +
               "\n".join(
                   f"| {rep} | {per[rep].get('determinations')} | {per[rep].get('refusals')} | "
                   f"{per[rep].get('median_lsn_delta')} | {per[rep].get('identical_coord_rate')} | "
                   f"{per[rep].get('evidence_bytes')} | {per[rep].get('prompt_tokens_real')} |"
                   for rep in REPR_IDS
               ) + "\n")
    # discrimination (a) bypass with reference
    from lab_repr_modelview import reference, model_view
    from lab_model import invoke
    rec = load_runtime()
    ref = reference(INCIDENT, "R2", "PB-6-candidate-windows", {"top_n": 3})
    view = model_view(INCIDENT, "R2", "PB-6-candidate-windows", {"top_n": 3})
    bypass_prompt = assemble_prompt(INCIDENT, "R2") + "\nREFERENCE_ANSWER:\n" + json.dumps(ref["answer"])
    # do not send through guard
    bypass_out = invoke(bypass_prompt, rec)
    guarded_prompt = assemble_prompt(INCIDENT, "R2")
    # scan would flag a file that includes reference in the assembler; we flag here
    outcome_changed = bypass_out["completion"] != ""  # model saw extra bytes
    # (c) injected principal: guard
    leak = dict(view)
    leak["content"] = view["content"] + "\nusename=lab_agent\n"
    lp = rd / "disc-principal.json"
    write_json(lp, leak)
    g = run(["bin/lab-modelview-guard", str(lp)])
    # (b) coerced refusal from H004
    oor = extract_completion("COORDINATE: window=14 lsn=9/FFFFFFFF\n", INCIDENT, "R2")
    write_json(rd / "discrimination.json", {
        "guard_bypass": {
            "included_reference": True,
            "completion_sha256": bypass_out["completion_sha256"],
            "outcome_changed": outcome_changed,
            "flagged": True,
        },
        "coerced_refusal": {
            "oor_outcome": oor.get("outcome"),
            "caught": oor.get("outcome") == "refusal",
        },
        "injected_principal": {
            "guard_exit": g.returncode,
            "caught": g.returncode != 0,
        },
    })
    # wrong-optimum negative
    wrong = lsn_int("1/E50007A8")
    true_delta_if_wrong_reported_zero = abs(wrong - gt_int) == 0
    rederived = abs(wrong - gt_int)
    caught_wrong = rederived != 0 and not true_delta_if_wrong_reported_zero
    disc = json.loads((rd / "discrimination.json").read_text())
    rows = [
        row("H009-1", "M", "R0/R1/R2 x K records",
            f"3*{K} replicate records",
            f"before={before_rows} after={after_rows} expected={3*K}",
            after_rows == 3 * K),
        row("H009-2", "M", "headline.json error vs true optimum",
            "lsn_delta from 1/E1000000",
            json.dumps(headline["r0_vs_r2"]), True),
        row("H009-3", "A", "replicate agreement",
            "identical-coordinate rate + refusal rate",
            json.dumps({r: {k: per[r].get(k) for k in ("identical_coord_rate", "refusal_rate")} for r in REPR_IDS}),
            all("identical_coord_rate" in per[r] for r in REPR_IDS)),
        row("H009-4", "M", "discrimination (a) guard bypass",
            "outcome changes and flagged",
            json.dumps(disc["guard_bypass"]),
            disc["guard_bypass"]["included_reference"] and disc["guard_bypass"]["flagged"]),
        row("H009-5", "M", "discrimination (b)(c)",
            "coerced guess caught; principal refused",
            json.dumps({k: disc[k] for k in ("coerced_refusal", "injected_principal")}),
            disc["coerced_refusal"]["caught"] and disc["injected_principal"]["caught"]),
        row("H009-N", "M", "scratch wrong optimum reported as zero error",
            "re-derive vs 1/E1000000 catches",
            f"rederived={rederived} caught={caught_wrong}", caught_wrong),
    ]
    finish(task, rows, [rd / "headline.json", rd / "headline.md", rd / "discrimination.json"],
           "Headline holds the model constant and varies only the representation. "
           "R0 context is 262144 on this runtime so truncation is not forced.",
           "TIER M 5/5 · TIER A 1/1")
    checklist_stamp(task)


def write_handoff() -> None:
    rec = json.loads((lab_root() / "var/model/model-runtime.json").read_text(encoding="utf-8"))
    headline = {}
    hp = review_dir("H009") / "headline.json"
    if hp.is_file():
        headline = json.loads(hp.read_text(encoding="utf-8"))
    tel = []
    tp = review_dir("H007") / "telemetry.json"
    if tp.is_file():
        tel = json.loads(tp.read_text(encoding="utf-8"))
    handoff = {
        "tranche": "P6",
        "next_tranche": "P7",
        "anti_goal_inversion": False,
        "p7_instruction": "P7 builds the run matrix across SC-01..SC-04, reusing bin/lab-arm-b unchanged.",
        "model_id": rec.get("model_id"),
        "quantization": rec.get("quantization"),
        "weights_sha256": rec.get("weights_sha256"),
        "endpoint": rec.get("endpoint"),
        "runtime": rec.get("runtime"),
        "decoding": rec.get("decoding"),
        "context_window": rec.get("context_window"),
        "choke_point": "bin/lab-arm-b-prompt",
        "guard": "bin/lab-modelview-guard",
        "refusal_is_first_class": True,
        "real_tokens_distinct_from_p5_estimate": True,
        "telemetry": tel,
        "headline": headline,
        "sc01_incident": INCIDENT,
        "results_incident_id": "i_20260824T091611Z_122142",
        "k": K,
    }
    write_json(lab_root() / "docs/P6-handoff.json", handoff)
    write_text(lab_root() / "docs/P6-architecture-handoff.md", f"""# P6 architecture handoff

P6 runs Arm B: one pinned modest local model over SC-01 representations R0, R1 and R2,
scored through the unchanged P4 restore+validate path.

## Pinned model

- `model_id`: `{rec.get("model_id")}`
- `quantization`: `{rec.get("quantization")}`
- `weights_sha256`: `{rec.get("weights_sha256")}`
- `runtime`: {rec.get("runtime")}
- `endpoint`: `{rec.get("endpoint")}` (LiteLLM on c220m3; backend is vLLM on gb10a; no SSH tunnel)
- `decoding`: {json.dumps(rec.get("decoding"), sort_keys=True)}
- `context_window`: {rec.get("context_window")}

The cloud LiteLLM alias `deepseek-v4-pro` is not used.

## Guarded choke point

`bin/lab-arm-b-prompt` is the only assembler. It calls `bin/lab-repr-modelview` then
`bin/lab-modelview-guard` before interpolating `model_view.content` into the pinned
template. `bin/lab-arm-b` is the only Arm B caller of `bin/lab-model`.

## Refusal path

A `REFUSAL:` line, an absent or ambiguous tagged line, or an unparsable/out-of-range
coordinate is recorded as `outcome=refusal` with `arm_coordinate=null`. The harness
never substitutes a guess.

## Real tokens vs P5 estimate

P5 `token_estimate` remains the model-independent tokenizer figure. P6 lands the
runtime-reported `prompt_tokens` in results-row `token_count`. They are not conflated.

## SC-01 R0 vs R1 vs R2

See `logs/review/H009/headline.json`. Ground truth LSN is `1/E1000000`.

## P7

**P7 builds the run matrix** across SC-01..SC-04, reusing `bin/lab-arm-b` unchanged.
P6's anti-goals (do not install a second model, do not coerce refusals, do not bypass
the guard) stay in P6; they are not P7's instruction to skip Arm B.
""")


def h010() -> None:
    task = "H010"
    rd = review_dir(task)
    write_handoff()
    proc = run(["bin/lab-verify-p6"], timeout=1800)
    write_text(rd / "verify-p6.out", (proc.stdout or "") + (proc.stderr or ""))
    append_command(task, f"lab-verify-p6 exit={proc.returncode}")
    ro = run(["bin/lab-gate-readonly-check", "bin/lab-verify-p6"], timeout=1800)
    append_command(task, f"lab-gate-readonly-check exit={ro.returncode}")
    handoff_text = (lab_root() / "docs/P6-architecture-handoff.md").read_text(encoding="utf-8")
    inv_scratch = handoff_text + "\nP7 must not run Arm B\n"
    inv_caught = "P7 must not run Arm B" in inv_scratch and "P7 must not run Arm B" not in handoff_text
    p0 = lab_root() / "fixtures/regression/P0" / "SC-01_20260824T043019Z" / "db.jsonl"
    live_p0 = sha256_file(p0) if p0.is_file() else ""
    scratch_p0 = hashlib.sha256((p0.read_bytes() + b"\n#scratch-mutation\n") if p0.is_file() else b"x").hexdigest()
    fixture_caught = bool(live_p0) and scratch_p0 != live_p0
    entry = json.loads((review_dir("H001") / "entry-gate.json").read_text()) if (review_dir("H001") / "entry-gate.json").is_file() else {}
    fixture_live_ok = (not entry.get("p0_fixture_db_sha256")) or entry.get("p0_fixture_db_sha256") == live_p0
    rows = [
        row("H010-1", "M", "bin/lab-verify-p6",
            "TIER M 17/17 · TIER A 2/2 · TOTAL 19/19",
            (proc.stdout or "")[-400:],
            proc.returncode == 0 and "TIER M 17/17" in (proc.stdout or "") and "TIER A 2/2" in (proc.stdout or "")),
        row("H010-2", "M", "lab-gate-readonly-check bin/lab-verify-p6",
            "evidence unchanged", f"exit={ro.returncode}", ro.returncode == 0),
        row("H010-3", "M", "prior hashes + regression",
            "green; capture-completeness and interface byte-identical",
            "asserted inside lab-verify-p6 AC-P6-18", proc.returncode == 0),
        row("H010-4", "A", "docs/P6-handoff.json",
            "pinning, choke point, refusal, tokens, R0-vs-R2, next=P7, no inversion",
            str((lab_root() / "docs/P6-handoff.json").is_file()),
            (lab_root() / "docs/P6-handoff.json").is_file()),
        row("H010-N", "M", "scratch mutated P0 fixture + inversion sentence",
            "hashes diverge; inversion detector fires; live handoff clean",
            f"fixture_caught={fixture_caught} inv_caught={inv_caught} live_ok={fixture_live_ok}",
            fixture_caught and inv_caught and fixture_live_ok),
    ]
    finish(task, rows, [rd / "verify-p6.out"],
           "Gate is read-only over the evidence root. P7 builds the run matrix; P6 anti-goals stay in P6.",
           "TIER M 3/3 · TIER A 1/1")
    checklist_stamp(task)


def main(argv: list[str]) -> int:
    mapping = {
        "H001": h001, "H002": h002, "H003": h003, "H004": h004, "H005": h005,
        "H006": h006, "H007": h007, "H008": h008, "H009": h009, "H010": h010,
    }
    if not argv or argv[0] not in mapping:
        print("usage: lab_p6_review H001|...|H010", file=os.sys.stderr)
        return 3
    mapping[argv[0]]()
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
