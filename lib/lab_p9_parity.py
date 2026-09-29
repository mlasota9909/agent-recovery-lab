"""lab-p9-parity (N003): prove what a model sees is set by the REPRESENTATION,
never by the model, and that the R0/R1/R2 artefacts are unchanged since P5/P5.1.

The anti-artefact invariant is structural: model identity is not an input to
lab-repr-modelview or lab-arm-b-prompt, so for a fixed representation the guarded
model_view and the assembled prompt are byte-identical across every model. This
module makes that mechanical rather than asserted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, die, write_json
from lab_p51 import ARTEFACT_HASHES, artefacts_byte_identical
from lab_p9 import REPR_IDS, load_model_set, root, sha256_text
from lab_repr import HEADLINE

PROBE = "PB-6-candidate-windows"
PARAMS = {"top_n": 3}


def _run(name: str, argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    return subprocess.run([str(root() / "bin" / name), *argv], cwd=str(root()),
                          text=True, capture_output=True, check=False, env=env, input=stdin)


def _skeleton(obj: object) -> object:
    """Keys + value types; content and telemetry collapsed to their type name."""
    if isinstance(obj, dict):
        return {k: (_skeleton(v) if k not in ("content", "telemetry") else type(v).__name__)
                for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_skeleton(obj[0])] if obj else []
    return type(obj).__name__


def model_view(incident: str, rep: str) -> dict:
    p = _run("lab-repr-modelview", [incident, rep, PROBE, json.dumps(PARAMS, separators=(",", ":"))])
    if p.returncode != 0:
        die(EXIT_ASSERT, p.stderr.strip() or "lab-repr-modelview failed")
    return json.loads(p.stdout)


def guard(view: dict, scratch: Path) -> tuple[int, str]:
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text(json.dumps(view, sort_keys=True) + "\n", encoding="utf-8")
    p = _run("lab-modelview-guard", [str(scratch)])
    return p.returncode, (p.stderr or p.stdout).strip()


def arm_b_prompt(incident: str, rep: str, as_model: str, scratch: Path) -> str:
    """Assemble the prompt as it would be for `as_model`. The alias is passed in
    the environment to demonstrate it has no effect on the assembled bytes."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib")
    env["MODEL_ID"] = as_model
    env["MODEL_ALIAS"] = as_model
    out = scratch / f"{rep}-{as_model}.prompt"
    p = subprocess.run([str(root() / "bin" / "lab-arm-b-prompt"), "--incident", incident,
                        "--representation", rep, "--out", str(out)],
                       cwd=str(root()), text=True, capture_output=True, check=False, env=env)
    if p.returncode != 0:
        die(EXIT_ASSERT, p.stderr.strip() or "lab-arm-b-prompt failed")
    return out.read_text(encoding="utf-8")


def run(incident: str, review: Path) -> dict:
    review.mkdir(parents=True, exist_ok=True)
    scratch = review / "scratch"
    scratch.mkdir(exist_ok=True)
    aliases = [m["alias"] for m in load_model_set().get("models", [])]

    per_rep = []
    parity_ok = True
    guard_answer_ok = True
    for rep in REPR_IDS:
        view = model_view(incident, rep)
        view_bytes = json.dumps(view, sort_keys=True, separators=(",", ":")) + "\n"
        view_sha = sha256_text(view_bytes)
        struct_sha = sha256_text(json.dumps(_skeleton(view), sort_keys=True))
        rc, msg = guard(view, scratch / f"{rep}.modelview.json")
        # assembled prompt per model alias
        prompt_shas = {a: sha256_text(arm_b_prompt(incident, rep, a, scratch)) for a in aliases}
        cross_model_identical = len(set(prompt_shas.values())) == 1
        # AC-P9-05: splice the reference answer into this representation's model_view
        spliced = dict(view)
        spliced["answer"] = {"candidates": [{"window_index": 14, "last_safe_lsn_int": 8053066984}]}
        arc, amsg = guard(spliced, scratch / f"{rep}.spliced-answer.json")
        answer_refused = arc != 0
        guard_answer_ok = guard_answer_ok and answer_refused
        parity_ok = parity_ok and cross_model_identical and rc == 0
        per_rep.append({
            "representation": rep,
            "model_view_sha256": view_sha,
            "structural_digest": struct_sha,
            "guard_rc": rc,
            "guard_msg": msg,
            "assembled_prompt_sha256_by_model": prompt_shas,
            "cross_model_prompt_identical": cross_model_identical,
            "spliced_answer_guard_rc": arc,
            "spliced_answer_refused": answer_refused,
        })

    artefacts = artefacts_byte_identical()
    payload = {
        "incident": incident,
        "headline_incident": HEADLINE,
        "models": aliases,
        "note": ("model identity is not an argument to lab-repr-modelview or "
                 "lab-arm-b-prompt; the assembled bytes are model-invariant by "
                 "construction, which is the anti-artefact defence."),
        "per_representation": per_rep,
        "interface_parity_ok": parity_ok,
        "guard_blocks_reference_answer": guard_answer_ok,
        "artefact_hashes": {
            "pinned": ARTEFACT_HASHES,
            "live": artefacts["live"],
            "byte_identical_to_P5_P5.1_close": artefacts["ok"],
        },
        "ok": parity_ok and guard_answer_ok and artefacts["ok"],
    }
    write_json(review / "interface-parity.json", payload)
    write_json(review / "artefact-hashes.json", artefacts)
    return payload


def negative(incident: str, review: Path) -> dict:
    """Inject a per-model structural field into one model_view: parity flags it and
    the guard refuses (unexpected key)."""
    scratch = review / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    view = model_view(incident, "R2")
    tampered = dict(view)
    tampered["model_hint"] = "deepseek-v4-flash"        # a per-model structural field
    struct_clean = sha256_text(json.dumps(_skeleton(view), sort_keys=True))
    struct_tampered = sha256_text(json.dumps(_skeleton(tampered), sort_keys=True))
    rc, msg = guard(tampered, scratch / "R2.per-model-field.json")
    caught = rc != 0 and struct_clean != struct_tampered
    rec = {
        "injected_field": "model_hint",
        "structural_digest_clean": struct_clean,
        "structural_digest_tampered": struct_tampered,
        "structural_digest_changed": struct_clean != struct_tampered,
        "guard_rc": rc,
        "guard_msg": msg,
        "parity_gate_red": caught,
        "ok": caught,
    }
    write_json(review / "negative-per-model-field.json", rec)
    return rec


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-parity")
    p.add_argument("--incident", default=HEADLINE)
    p.add_argument("--review", default=str(root() / "logs" / "review" / "N003"))
    p.add_argument("--negative", action="store_true")
    args = p.parse_args(argv)
    review = Path(args.review)
    if args.negative:
        rec = negative(args.incident, review)
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0 if rec["ok"] else EXIT_ASSERT
    rec = run(args.incident, review)
    print(json.dumps({"ok": rec["ok"], "interface_parity_ok": rec["interface_parity_ok"],
                      "guard_blocks_reference_answer": rec["guard_blocks_reference_answer"],
                      "artefacts_byte_identical": rec["artefact_hashes"]["byte_identical_to_P5_P5.1_close"]},
                     indent=2, sort_keys=True))
    return 0 if rec["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
