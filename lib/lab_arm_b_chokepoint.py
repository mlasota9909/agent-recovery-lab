"""Repository scan: one prompt assembler; Arm B calls lab-model only via the driver."""
from __future__ import annotations

import json
import re
from pathlib import Path

from lab_paths import lab_root

MODEL_CALL_RE = re.compile(r"""bin/lab-model(?!-[A-Za-z])|['\"]lab-model['\"]""")

ALLOWED_ASSEMBLERS = {"bin/lab-arm-b-prompt", "lib/lab_arm_b_prompt.py"}
ALLOWED_MODEL_CALLERS_BIN = {"bin/lab-model", "bin/lab-arm-b"}


def scan(root: Path | None = None) -> dict:
    root = root or lab_root()
    assemblers = []
    callers = []
    # Assemblers: the known implementation, plus any extra bin/* that embeds the content markers.
    prompt_impl = root / "lib" / "lab_arm_b_prompt.py"
    if prompt_impl.is_file():
        assemblers.append("lib/lab_arm_b_prompt.py")
    prompt_bin = root / "bin" / "lab-arm-b-prompt"
    if prompt_bin.is_file():
        assemblers.append("bin/lab-arm-b-prompt")
    extra_asm = []
    extra_call = []
    bindir = root / "bin"
    if bindir.is_dir():
        for path in sorted(bindir.iterdir()):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if rel not in ALLOWED_ASSEMBLERS and ("<<<ARM_B_CONTENT" in text or "arm-b-prompt.txt" in text):
                extra_asm.append(rel)
                assemblers.append(rel)
            if MODEL_CALL_RE.search(text):
                callers.append(rel)
                if rel not in ALLOWED_MODEL_CALLERS_BIN and "lab-arm-b-prompt" not in rel:
                    extra_call.append(rel)
    arm_b_lib = root / "lib" / "lab_arm_b.py"
    if arm_b_lib.is_file() and MODEL_CALL_RE.search(arm_b_lib.read_text(encoding="utf-8")):
        callers.append("bin/lab-arm-b")
        callers.append("lib/lab_arm_b.py")
    libdir = root / "lib"
    if libdir.is_dir():
        for path in sorted(libdir.glob("*.py")):
            rel = str(path.relative_to(root))
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if MODEL_CALL_RE.search(text) and rel not in {
                "lib/lab_model.py", "lib/lab_arm_b.py", "lib/lab_p6_review.py",
                "lib/lab_verify_p6.py", "lib/lab_arm_b_chokepoint.py",
                "lib/lab_p61_review.py", "lib/lab_verify_p61.py", "lib/lab_model_containment.py",
            }:
                extra_call.append(rel)
                callers.append(rel)
    def uniq(rows: list[str]) -> list[str]:
        seen, out = set(), []
        for r in rows:
            if r not in seen:
                seen.add(r)
                out.append(r)
        return out
    return {
        "prompt_assemblers": uniq(assemblers),
        "lab_model_callers": uniq(callers),
        "bypass_found": bool(extra_asm or extra_call),
        "extra_assemblers": extra_asm,
        "extra_callers": extra_call,
    }


def main(argv: list[str]) -> int:
    rec = scan()
    print(json.dumps(rec, indent=2, sort_keys=True))
    return 1 if rec["bypass_found"] else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
