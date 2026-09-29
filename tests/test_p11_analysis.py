"""Rebuild all P11 statistics/figures; refuse each frozen-contract mutation."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from lab_p11 import CONTRACTS, contract_dir, read_json, review, root, rows, sha256_file, write_json
from lab_p11_stats import interpretations, lint


def main(argv=None):
    required = root() / 'logs/review/R001/preregistration.json'
    if not required.is_file():
        print(json.dumps({"ok": True, "skipped": "needs the development repository's P10/P11 records: " + str(required.relative_to(root()))}))
        return 0
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=review('R005') / 'checks.json')
    a = p.parse_args(argv)
    scratch = a.out.parent / 'scratch/analysis-check'
    scratch.mkdir(parents=True, exist_ok=True)
    commands, hashes = [], {}
    for name in ('first', 'second'):
        out = scratch / name
        command = [str(root() / 'bin/lab-p11-stats'), '--out-dir', str(out)]
        proc = subprocess.run(command, text=True, capture_output=True)
        commands.append({'command': command, 'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr})
        assert proc.returncode == 0, proc.stderr
        hashes[name] = {ext: sha256_file(out / f'p11-rescore.{ext}') for ext in ('json', 'md', 'svg', 'png')}
    committed = {ext: sha256_file(root() / f'analysis-out/analysis/p11-rescore.{ext}') for ext in ('json', 'md', 'svg', 'png')}
    assert hashes['first'] == hashes['second'] == committed, 'regeneration differs'
    negatives = []
    for name in CONTRACTS:
        copied = scratch / ('contracts-' + name)
        if copied.exists():
            shutil.rmtree(copied)
        shutil.copytree(contract_dir(), copied)
        p = copied / name
        p.write_text(p.read_text() + '\n<!-- external negative test -->\n')
        dest = scratch / ('refused-' + name)
        command = [str(root() / 'bin/lab-p11-stats'), '--contracts-dir', str(copied), '--out-dir', str(dest)]
        proc = subprocess.run(command, text=True, capture_output=True)
        assert proc.returncode != 0 and not dest.exists(), 'tampered contract did not halt before output'
        negatives.append({'file': name, 'exit': proc.returncode, 'stderr': proc.stderr, 'no_output': True})
    r = read_json(root() / 'analysis-out/analysis/p11-rescore.json')
    rr = rows()
    anchor = [x for x in rr if x['analysis_selected'] and x['representation'] == 'R0' and
              x['scale_target'] == 10000 and x['grammar_outcome'] == 'accepted']
    assert r['H4']['accepted'] == len(anchor)
    assert r['H4']['correct'] == sum(x['verdict'] == 'correct' for x in anchor)
    if r['H4']['bootstrap'] is not None:
        assert r['H4']['bootstrap']['n_resamples'] == 10000 and r['H4']['bootstrap']['seed'] == 42
        assert (r['H4']['status'] == 'HOLDS') == (r['H4']['bootstrap']['ci_low'] > .5)
    for x in r['H1-R']['per_model'].values():
        if x['bootstrap'] is not None:
            assert x['bootstrap']['alpha'] == .05 / 3
            assert (x['status'] == 'HOLDS') == (x['bootstrap']['ci_low'] > 0)
    assert r['interpretation'] == interpretations()[r['branch']]
    text = (root() / 'analysis-out/analysis/p11-rescore.md').read_text()
    assert lint(text, r)['ok']
    assert not lint(text + '\nThere is an accuracy cliff.\n', r)['ok']
    result = {'ok': True, 'commands': commands, 'regeneration_hashes': hashes,
              'published_hashes': committed, 'digest_negative_tests': negatives,
              'lint': lint(text, r), 'unsupported_claim_negative_caught': True,
              'hypotheses': {k: r[k] for k in ('H4', 'H1-R', 'H3-R')}}
    write_json(a.out, result)
    print(json.dumps({'ok': True, 'byte_identical_outputs': 4, 'contract_mutants_refused': len(negatives)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
