"""P11 terminal gate: actual CLI rebuilds, explicit tier totals and immutable prior stores."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from lab_p11 import (GRAMMAR, PLAN, combined, compare, contract_dir, dumps, entry, head, prereg_check,
                     protected_manifest, read_json, reserved_r006, review, root, rows, sha256_file, sha256_text, utc,
                     write_json)


def call(command: list[str], out: Path, env=None, timeout=3600) -> dict:
    proc = subprocess.run(command, text=True, capture_output=True, cwd=root(), env=env, timeout=timeout)
    rec = {'command': command, 'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
    write_json(out, rec)
    return rec


def prior_gate(out: Path) -> dict:
    """Run unchanged P10 code against an isolated copy of its original artefact namespace.

    Fixed prior review paths point inside scratch. No prior gate result is patched.
    Archive files are a read-only input; this gate never runs a live regression/reset.
    """
    mirror = out.parent / 'scratch/prior-gates'
    if mirror.exists():
        shutil.rmtree(mirror)
    mirror.mkdir(parents=True)
    base_commit = read_json(review('R001') / 'preregistration.json')['producer_commit']
    # R001's producer is the first P11 source commit. Its parent is the untouched
    # pre-P11 tree. Only the isolated namespace uses that historic tree.
    prior_commit = subprocess.check_output(['git', 'rev-parse', base_commit + '^'], text=True).strip()
    p = subprocess.Popen(['git', 'archive', prior_commit], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=p.stdout, mode='r|') as archive:
        archive.extractall(mirror, filter='data')
    if p.wait() != 0:
        raise RuntimeError('could not copy pre-P11 source tree')
    # P8's plotting/analysis modules are locally retained, not in git archive.
    # Copy their actual bytes as well; no fallback implementation is substituted.
    shutil.copytree(root() / 'analysis', mirror / 'analysis', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    baseline = read_json(review('R001') / 'prior-evidence-manifest.json')
    for name, expected in baseline['entries'].items():
        if name.startswith('archive/'):
            continue
        src, dst = root() / name, mirror / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        if src.is_symlink():
            dst.symlink_to(os.readlink(src))
        else:
            shutil.copy2(src, dst)
    archive_link = mirror / 'archive'
    if archive_link.exists() or archive_link.is_symlink():
        raise RuntimeError('unexpected archive in source archive')
    archive_link.symlink_to(root() / 'archive', target_is_directory=True)
    # All ordinary new writes are now under R007. Preserve the source lab.env
    # byte-for-byte; change only the private scratch copy's workspace paths.
    config = mirror / 'etc/lab.env'
    config.write_text(config.read_text().replace(str(root()), str(mirror)))
    env = os.environ.copy()
    env.update(LAB_ROOT=str(mirror), PYTHONPATH=str(mirror / 'lib') + os.pathsep + str(mirror / 'analysis'),
               PYTHONDONTWRITEBYTECODE='1', LAB_READONLY_CHECK='1')
    # Clear inherited roots so the legacy wrapper uses its private configuration.
    for key in ('EVIDENCE_ROOT', 'ARCHIVE_ROOT', 'ARCHIVE_CURRENT', 'RESULTS_ROOT', 'LAB_REPR_ROOT'):
        env.pop(key, None)
    same_source = {name: sha256_file(root() / name) == sha256_file(mirror / name)
                   for name in ('bin/lab-verify-p10', 'lib/lab_verify_p10.py', 'lib/lab_p10.py',
                                'lib/lab_p10_stats.py', 'lib/lab_p9_statlib.py')}
    if not all(same_source.values()):
        raise RuntimeError('prior gate code differs from the real unchanged CLI')
    command = [str(mirror / 'bin/lab-verify-p10')]
    rec = call(command, out.parent / 'prior-gate-command.json', env)
    path = mirror / 'logs/review/Q007/gate.json'
    gate = read_json(path) if path.exists() else None
    result = {'ok': rec['exit'] == 0 and gate is not None and gate['ok'], 'exit': rec['exit'],
              'source_commit': prior_commit, 'source_bytes_identical': same_source,
              'isolation': str(mirror.relative_to(root())), 'summary': gate,
              'stdout_tail': rec['stdout'].splitlines()[-5:], 'stderr_tail': rec['stderr'][-1000:],
              'original_regression_sha256': sha256_file(root() / 'logs/review/Q007/regression.json'),
              'copied_regression_sha256': sha256_file(mirror / 'logs/review/Q007/regression.json')}
    write_json(out, result)
    return result


def confirm_check() -> dict:
    from lab_p11_rescore import trigger, parse_cli, score_position
    from lab_p10 import scaled_root, CONTEXT_WINDOWS, MAX_TOKENS
    from lab_p10_sweep import preflight_path
    from lab_p9 import evaluate_containment, load_model_set, P9_ENDPOINT
    rr = rows()
    wanted = trigger(rr)
    actual = [r for r in rr if not r['no_new_model_call']]
    att = read_json(review('R004') / 'attestation.json')
    errors = []
    if wanted != read_json(review('R003') / 'rerun-trigger.json'):
        errors.append('trigger drift')
    if att['cells'] != wanted['cells'] or att['new_calls'] != len(actual) or len(actual) != wanted['planned_new_calls']:
        errors.append('batch count/cells mismatch')
    registry = {r['alias']: r for r in load_model_set()['models']}
    for cell in wanted['cells']:
        counted = [r for r in actual if (r['model_id'], r['scale_target'], r['representation']) ==
                   (cell['model_id'], cell['scale_target'], 'R0')]
        if len(counted) != cell['top_up_n']:
            errors.append('unplanned or missing per-cell calls')
    for r in actual:
        p = root() / r['model_record']
        model = read_json(p)
        identity = read_json(p.with_name('identity.json'))
        start = read_json(p.with_name('request-started.json'))
        prompt = scaled_root(r['scale_target']) / 'prompts/R0.prompt'
        pre = read_json(preflight_path(r['model_id']))['cells'][f"{r['scale_target']}|R0"]
        ok = (sha256_file(p) == r['model_record_sha256'] and sha256_file(prompt) == model['prompt_sha256'] == pre['prompt_sha256']
              and model['prompt'] == prompt.read_text() and sha256_text(model['completion']) == r['completion_sha256']
              and pre['feasible'] and identity['ok'] and model['seed'] == 42 and model['temperature'] == 0
              and model['finish_reason'] == 'stop' and r['no_new_model_call'] is False
              and model['prompt_tokens'] + MAX_TOKENS <= CONTEXT_WINDOWS[r['model_id']]
              and start['harness_commit'] == r['invocation_harness_commit'])
        contain = evaluate_containment(registry[r['model_id']], P9_ENDPOINT,
                                       observed_public_peers=model['outbound_public_peers'])
        ok = ok and contain['containment_verified'] and model['containment_verified'] and r['containment_verified']
        parsed = parse_cli(model['completion'], r['scale_target'], 'R0', review('R007') / 'scratch/confirm-check')
        ok = ok and all(r[k] == v for k, v in parsed.items())
        if parsed['grammar_outcome'] == 'accepted':
            score = score_position(r['scale_target'], parsed['chosen_lsn_int'], r['oracle_optimum_lsn_int'])
            ok = ok and all(r[k] == v for k, v in score.items())
        if not ok:
            errors.append(r['rescore_run_id'])
    if not wanted['fired'] and (not att.get('skipped_by_rule') or actual):
        errors.append('false skip attestation')
    return {'ok': not errors, 'errors': errors, 'planned_calls': wanted['planned_new_calls'], 'actual_calls': len(actual),
            'tier': 'A', 'basis': 'recorded request/response and containment observations, mechanically checked'}


def readonly_negative(out: Path) -> dict:
    scratch = out.parent / 'scratch/readonly-negative'
    scratch.mkdir(parents=True, exist_ok=True)
    p = scratch / 'scaling-runs.jsonl'
    shutil.copy2(root() / 'results/scaling-runs.jsonl', p)
    original = {'entries': {'results/scaling-runs.jsonl': entry(p)}, 'digest': sha256_file(p)}
    data = bytearray(p.read_bytes()); data[0] ^= 1; p.write_bytes(data)
    changed = {'entries': {'results/scaling-runs.jsonl': entry(p)}, 'digest': sha256_file(p)}
    result = compare(original, changed)
    write_json(out, {'ok': not result['ok'], 'comparison': result, 'original_untouched': True})
    return {'ok': not result['ok'], 'comparison': result}


def memo(analysis: dict, checks: list[dict], readonly: dict, prior: dict) -> None:
    from lab_p11_stats import PRETTY
    rv = review('R007')
    all_ok = all(c['ok'] for c in checks)
    lines = ['# P11 close-out record', '',
             '**Status: ' + ('complete.' if all_ok else 'not complete; unmet acceptance requirements remain.') + '**', '',
             '## Realised interpretation', '', analysis['interpretation'], '',
             '| Test | Outcome |', '|---|---|']
    for name in ('H4', 'H1-R', 'H3-R'):
        lines.append(f"| {name} | {analysis[name]['status']} |")
    h4 = analysis['H4']
    lines += ['', f"H4: {h4['correct']}/{h4['accepted']} accepted anchor answers correct; "
              f"95% interval [{h4['bootstrap']['ci_low']:.4f}, {h4['bootstrap']['ci_high']:.4f}].", '',
              '## Audit and calls', '',
              f"{analysis['core_audit']['observed_occurrences']} saved occurrences were re-parsed, including "
              f"{analysis['core_audit']['historical_occurrences']} retained historical records. "
              f"R004 authorised and recorded {analysis['confirmatory']['new_calls']} additional contained call(s).", '',
              '| Representation | Model | Scale | Before | After | Count |', '|---|---|---|---|---|---|']
    for c in analysis['core_audit']['outcome_changes_by_cell']:
        if c['before'] != c['after']:
            lines.append(f"| {c['representation']} | {PRETTY[c['model_id']]} | {c['scale_target']} | {c['before']} | {c['after']} | {c['count']} |")
    lines += ['', '## Read-only proof', '',
              f"Prior-store comparison: {'PASS' if readonly['ok'] else 'FAIL'}. "
              f"{readonly['files_before']} pre-existing files/links were compared, including the full archive bytes. "
              f"Before digest: `{readonly['before_digest']}`. After digest: `{readonly['after_digest']}`.", '',
              'The original P10 sidecars, P9 sweep, prior analyses and prior review records were preserved. '
              'Prior gates ran in a scratch copy with identical gate source bytes. New outputs stayed under the P11 review tree.', '',
              '## Prior gate and unmet requirements', '',
              f"The unchanged P10 gate returned exit {prior.get('exit')}. "
              f"Its result was {'green' if prior.get('ok') else 'not green'}. See `prior-gate.json` for each actual check."]
    if not prior.get('ok'):
        lines += ['', 'The banked P10 regression already records a failed P0 live check. Its recorded cause is '
                  'an invalidated replication slot and a refused reset while seven older incident clusters are running. '
                  'P11 does not rewrite that record or reset the shared experiment to manufacture a green gate. '
                  'AC-P11-13 remains unmet. A compatible fresh prior-gate proof or an explicit change to that '
                  'requirement is needed for full close-out; no waiver has been applied.']
    lines += ['', '## Handoff', '',
              'The only downstream consumer is human review of the outputs. Use the actual H4/H1-R/H3-R '
              'outcomes and the limits beside the figure. H4 did not support the proposed general small-scale '
              'claim. The operator-review checkbox remains for the operator. This handoff does not prescribe '
              'a future experiment or carry an earlier non-goal forward as a future instruction.', '']
    (rv / 'close-out-memo.md').write_text('\n'.join(lines))
    write_json(rv / 'close-out.json', {'complete': all_ok, 'interpretation': analysis['interpretation'],
               'hypotheses': {k: analysis[k]['status'] for k in ('H4', 'H1-R', 'H3-R')},
               'outcome_changes': analysis['core_audit']['outcome_changes_by_cell'],
               'new_calls': analysis['confirmatory']['new_calls'], 'readonly_ok': readonly['ok'],
               'prior_gate_ok': prior.get('ok', False), 'downstream_consumer': 'human review',
               'human_review_claimed': False})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='lab-verify-p11')
    p.add_argument('--prior-only', action='store_true', help='run only the isolated unchanged P10 gate')
    a = p.parse_args(argv)
    rv = review('R007'); rv.mkdir(parents=True, exist_ok=True)
    if a.prior_only:
        r = prior_gate(rv / 'prior-gate.json')
        print(dumps({'ok': r['ok'], 'exit': r['exit'], 'stdout_tail': r['stdout_tail']}), end='')
        return 0 if r['ok'] else 1
    checks = []

    def record(n, tier, name, ok, observed):
        checks.append({'ac': f'AC-P11-{n:02d}', 'tier': tier, 'name': name, 'ok': bool(ok), 'observed': observed})
        print(f"{'PASS' if ok else 'FAIL'} [{tier}] AC-P11-{n:02d} {name}", flush=True)

    pre = prereg_check()
    record(1, 'M', 'grammar and analysis were frozen before every row', pre['ok'], pre)
    gr = call([sys.executable, str(root() / 'tests/test_p11_grammar.py'), '--out', str(rv / 'grammar.json')], rv / 'grammar-command.json')
    g = read_json(rv / 'grammar.json') if gr['exit'] == 0 else {}
    record(2, 'M', 'real CLI parses rebuild byte-identically', gr['exit'] == 0 and g.get('ok'), g.get('cases', gr))
    record(3, 'M', 'input/environment taint and external oracle mutants', g.get('answer_blind', {}).get('identical') and
           sum(x['rejected'] for x in g.get('negative_tests', []) if 'oracle' in x['mutant']) == 2, g.get('answer_blind'))
    record(4, 'M', 'representation parity and external branch mutant', g.get('symmetry', {}).get('identical') and
           any(x['mutant'] == 'representation-branch' and x['rejected'] for x in g.get('negative_tests', [])), g.get('symmetry'))
    sr = call([sys.executable, str(root() / 'tests/test_p11_rescore.py'), '--out', str(rv / 'rescore.json')], rv / 'rescore-command.json')
    s = read_json(rv / 'rescore.json') if sr['exit'] == 0 else {}
    record(5, 'M', 'every occurrence re-parsed/re-scored; unchanged scored verdicts agree; flipped verdict caught',
           sr['exit'] == 0 and s.get('ok'), s.get('audit', sr))
    record(6, 'M', 'zero actual corrupt recoveries and actual P4 damage case surfaced',
           s.get('audit', {}).get('safety', {}).get('ok') and s.get('negative_corrupt', {}).get('verdict') == 'incorrect_corrupt',
           s.get('negative_corrupt'))
    ar = call([sys.executable, str(root() / 'tests/test_p11_analysis.py'), '--out', str(rv / 'analysis.json')], rv / 'analysis-command.json')
    st = read_json(rv / 'analysis.json') if ar['exit'] == 0 else {}
    record(7, 'M', 'H1-R endpoint differences and Bonferroni intervals rebuilt', ar['exit'] == 0 and st.get('ok'), st.get('hypotheses', {}).get('H1-R', ar))
    record(8, 'M', 'H4 pooled mean and registered threshold rebuilt', ar['exit'] == 0 and st.get('ok'), st.get('hypotheses', {}).get('H4', ar))
    record(9, 'M', 'analysis refuses each original/amendment digest mutation',
           len(st.get('digest_negative_tests', [])) == 4 and all(x['exit'] != 0 for x in st['digest_negative_tests']), st.get('digest_negative_tests'))
    from lab_p11_stats import analyse, lint
    analysis = analyse()
    r006 = reserved_r006()
    r006_check = (r006.check(root(), analysis, lint) if r006 else
                  {'ok': False, 'violations': ['reserved R006 module is not present']})
    record(10, 'M', 'registered interpretation, reserved R006 check and byte-identical figures',
           ar['exit'] == 0 and r006_check['ok'],
           {'r006_check': r006_check, 'regenerated': st.get('published_hashes')})
    conf = confirm_check()
    record(11, 'A', 'conditional model calls match the recorded trigger and containment proof', conf['ok'], conf)
    print('Checking the unchanged P10 gate in a scratch copy...', flush=True)
    prior = prior_gate(rv / 'prior-gate.json')
    print('Hashing all prior stores, including archive bytes...', flush=True)
    after = protected_manifest()
    write_json(rv / 'prior-evidence-manifest-after.json', after)
    ro = compare(read_json(review('R001') / 'prior-evidence-manifest.json'), after)
    neg = readonly_negative(rv / 'readonly-negative.json')
    write_json(rv / 'readonly-proof.json', ro)
    record(12, 'M', 'all prior bytes/modes unchanged; scratch one-byte change rejected', ro['ok'] and neg['ok'], ro)
    record(13, 'M', 'prior P10 and chained gates green; actual outcome handed to human review', prior['ok'],
           {'prior_exit': prior.get('exit'), 'summary': prior.get('stdout_tail')})
    memo(analysis, checks, ro, prior)
    mm, aa = [r for r in checks if r['tier'] == 'M'], [r for r in checks if r['tier'] == 'A']
    mp, ap = sum(r['ok'] for r in mm), sum(r['ok'] for r in aa)
    result = {'ok': all(r['ok'] for r in checks), 'tier_m': f'{mp}/{len(mm)}', 'tier_a': f'{ap}/{len(aa)}',
              'checks': checks, 'total': f'{mp+ap}/{len(checks)}'}
    write_json(rv / 'gate.json', result)
    print(f"TIER M {mp}/{len(mm)} · TIER A {ap}/{len(aa)} · TOTAL {mp+ap}/{len(checks)}", flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
