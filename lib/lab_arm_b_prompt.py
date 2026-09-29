"""lab-arm-b-prompt: the single guarded prompt-assembly choke point."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, write_text
from lab_paths import lab_root

PROBE = "PB-6-candidate-windows"
PARAMS = {"top_n": 3}
CONTENT_BEGIN = "<<<ARM_B_CONTENT"
CONTENT_END = "ARM_B_CONTENT>>>"


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def template_path() -> Path:
    env_path = os.environ.get("ARM_B_PROMPT_TEMPLATE")
    return Path(env_path) if env_path else root() / "etc" / "arm-b-prompt.txt"


def run_bin(name: str, argv: list[str], stdin: str | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [str(root() / "bin" / name), *argv],
        cwd=str(root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=env, input=stdin,
    )


def fetch_model_view(incident: str, representation: str) -> dict:
    proc = run_bin("lab-repr-modelview", [incident, representation, PROBE, json.dumps(PARAMS, separators=(",", ":"))])
    if proc.returncode != 0:
        die(proc.returncode if proc.returncode in {1, 2, 3} else EXIT_ASSERT,
            proc.stderr.strip() or proc.stdout.strip() or "lab-repr-modelview failed")
    return json.loads(proc.stdout)


def guard_model_view(view: dict, scratch: Path) -> None:
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text(json.dumps(view, sort_keys=True) + "\n", encoding="utf-8")
    proc = run_bin("lab-modelview-guard", [str(scratch)])
    if proc.returncode != 0:
        die(EXIT_ASSERT, proc.stderr.strip() or proc.stdout.strip() or "lab-modelview-guard refused")


def render(content: str) -> str:
    path = template_path()
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: prompt template missing {path}")
    tmpl = path.read_text(encoding="utf-8")
    if "{content}" not in tmpl:
        die(EXIT_ASSERT, "assertion failed: prompt template lacks {content} placeholder")
    if tmpl.count("{content}") != 1:
        die(EXIT_ASSERT, "assertion failed: prompt template must interpolate content exactly once")
    return tmpl.replace("{content}", content)


def assemble(incident: str, representation: str, scratch_dir: Path | None = None) -> str:
    view = fetch_model_view(incident, representation)
    scratch = (scratch_dir or (root() / "var" / "arm_b" / "_guard")) / f"{incident}-{representation}.json"
    guard_model_view(view, scratch)
    content = view["content"]
    prompt = render(content)
    if CONTENT_BEGIN not in prompt or CONTENT_END not in prompt:
        die(EXIT_ASSERT, "assertion failed: assembled prompt missing content markers")
    return prompt


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-arm-b-prompt")
    p.add_argument("--incident", required=True)
    p.add_argument("--representation", required=True, choices=("R0", "R1", "R2"))
    p.add_argument("--out")
    args = p.parse_args(argv)
    prompt = assemble(args.incident, args.representation)
    if args.out:
        write_text(Path(args.out), prompt)
    sys.stdout.write(prompt if prompt.endswith("\n") else prompt + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
