"""P11 immutable inputs, preregistration and JSON utilities."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from lab_p10 import root, sha256_file, sha256_text, utc

SPEC = Path('sdd/specs/P11-answer-grammar-rescore')
GRAMMAR = ('answer-grammar.md', 'answer-grammar.amendment-1.md')
PLAN = ('rescore-analysis-plan.md', 'rescore-analysis-plan.amendment-1.md')
CONTRACTS = GRAMMAR + PLAN
S_STAR = {'gb10a-deepseek-v4-flash': 250000, 'alienware-qwen38-27b': 100000,
          'gympc-gemma4-26b': 50000}


def read_json(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')


def contract_dir() -> Path:
    return root() / SPEC / 'contracts'


def review(task: str) -> Path:
    return root() / 'logs/review' / task


def combined(names, directory: Path | None = None) -> str:
    d = directory or contract_dir()
    return sha256_text(''.join(f'{n}:{sha256_file(d / n)}\n' for n in names))


def head(clean: bool = False) -> str:
    if clean:
        dirty = subprocess.check_output(['git', '-C', str(root()), 'status', '--porcelain',
                                         '--untracked-files=no'], text=True)
        if dirty.strip():
            raise RuntimeError('Article XIV: tracked tree is dirty; commit before producing results')
    return subprocess.check_output(['git', '-C', str(root()), 'rev-parse', 'HEAD'], text=True).strip()


def row_path() -> Path:
    return root() / 'results/rescoring-runs.jsonl'


def rows(path: Path | None = None) -> list[dict]:
    p = path or row_path()
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def entry(p: Path) -> dict:
    st = p.lstat()
    if p.is_symlink():
        return {'link': os.readlink(p), 'mode': st.st_mode & 0o7777}
    return {'sha256': sha256_file(p), 'mode': st.st_mode & 0o7777, 'size': st.st_size}


def reserved_r006():
    """R006 is reserved; its output path and check live in a local-only module."""
    sys.path.insert(0, str(root() / 'analysis'))
    try:
        import r006_local
    except ImportError:
        return None
    return r006_local


def protected_manifest() -> dict:
    """All pre-existing experimental stores, including archive bytes and prior reviews."""
    r006 = reserved_r006()
    r006_outputs = {r006.OUTPUT} if r006 else set()
    paths = set()
    for r in ('evidence', 'results', 'incidents/scaled', 'var/repr', 'var/restore', 'var/arm_b',
              'fixtures', 'runtime', 'thesis', 'logs/review', 'archive', 'basebackup', 'backups'):
        for p in (root() / r).rglob('*'):
            rel = p.relative_to(root()).as_posix()
            if rel.startswith(tuple('logs/review/' + t + '/' for t in
                                    ('R001', 'R002', 'R003', 'R004', 'R005', 'R006', 'R007', 'P11'))):
                continue
            if (rel.startswith('results/rescoring-runs') or rel.startswith('thesis/analysis/p11-')
                    or rel.startswith('runtime/p11-') or rel in r006_outputs):
                continue
            if p.is_file() or p.is_symlink():
                paths.add(p)
    for d in (root() / 'sdd/specs').glob('P*'):
        if d == root() / SPEC:
            continue
        paths.update(p for p in (d / 'contracts').rglob('*') if p.is_file())
    paths.update(p for p in (root() / 'docs').glob('P*-*handoff.md') if p.is_file())
    paths.add(root() / 'etc/lab.env')
    entries = {p.relative_to(root()).as_posix(): entry(p) for p in sorted(paths)}
    return {'captured_utc': utc(), 'entries': entries, 'count': len(entries),
            'digest': sha256_text(dumps(entries))}


def compare(before: dict, after: dict) -> dict:
    a, b = before['entries'], after['entries']
    changed = sorted(k for k in a.keys() & b.keys() if a[k] != b[k])
    deleted, added = sorted(a.keys() - b.keys()), sorted(b.keys() - a.keys())
    return {'ok': not (changed or deleted or added), 'changed': changed, 'deleted': deleted,
            'added': added, 'before_digest': before['digest'], 'after_digest': after['digest'],
            'files_before': len(a), 'files_after': len(b)}


def prereg_check(results_dir: Path | None = None, contracts: Path | None = None) -> dict:
    """Fail closed on either contract, input drift or a row/file preceding the freeze."""
    results_dir = results_dir or root() / 'results'
    contracts = contracts or contract_dir()
    pre = read_json(review('R001') / 'preregistration.json')
    pinned = read_json(contract_dir() / 'frozen-hashes.json')
    live = {n: sha256_file(contracts / n) for n in CONTRACTS}
    digest_ok = live == pre['contracts'] == pinned['contracts']
    grammar, plan = combined(GRAMMAR, contracts), combined(PLAN, contracts)
    digest_ok = digest_ok and grammar == pre['grammar_digest'] == pinned['grammar_digest']
    digest_ok = digest_ok and plan == pre['analysis_plan_digest'] == pinned['analysis_plan_digest']
    tpre = datetime.fromisoformat(pre['preregistered_utc'].replace('Z', '+00:00'))
    violations = []
    for f in sorted(results_dir.glob('rescoring-runs*')):
        if not f.is_file():
            violations.append({'file': f.name, 'why': 'not a regular results file'})
            continue
        if datetime.fromtimestamp(f.stat().st_mtime, timezone.utc) <= tpre:
            violations.append({'file': f.name, 'why': 'mtime not after pre-registration'})
        if f.suffix != '.jsonl':
            continue
        for i, r in enumerate(rows(f), 1):
            try:
                tr = datetime.fromisoformat(r['row_utc'].replace('Z', '+00:00'))
                good = tr > tpre and r['grammar_digest'] == grammar and r['analysis_plan_digest'] == plan
            except (KeyError, TypeError, ValueError):
                good = False
            if not good:
                violations.append({'file': f.name, 'line': i, 'why': 'row time or frozen digest invalid'})
    input_ok = {n: sha256_file(root() / n) == h for n, h in pre['input_hashes'].items()}
    return {'ok': bool(digest_ok and not violations and all(input_ok.values())),
            'contracts_ok': bool(digest_ok), 'grammar_digest': grammar, 'analysis_plan_digest': plan,
            'frozen_before_data': not violations, 'violations': violations,
            'input_hashes_ok': input_ok, 'preregistered_utc': pre['preregistered_utc']}
