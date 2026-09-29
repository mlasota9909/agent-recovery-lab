"""Re-score all retained P10 completions without changing any P10 artefact."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from lab_p10 import INCIDENT, scaled_root, sha256_file, sha256_text, utc
from lab_p11 import (GRAMMAR, PLAN, S_STAR, combined, contract_dir, dumps, head, prereg_check,
                     read_json, review, root, row_path, rows, write_json)


def source_occurrences() -> list[tuple[int, dict, dict, str, str, bool]]:
    main_lines = (root() / 'results/scaling-runs.jsonl').read_text().splitlines()
    detail_lines = (root() / 'results/scaling-runs-detail.jsonl').read_text().splitlines()
    if len(main_lines) != len(detail_lines):
        raise RuntimeError('P10 main/detail occurrence counts disagree')
    latest, joined = {}, []
    for line, (rs, ds) in enumerate(zip(main_lines, detail_lines), 1):
        r, d = json.loads(rs), json.loads(ds)
        if r['scale_run_id'] != d['scale_run_id']:
            raise RuntimeError(f'P10 main/detail join differs on line {line}')
        latest[r['scale_run_id']] = line
        joined.append((line, r, d, sha256_text(rs + '\n'), sha256_text(ds + '\n')))
    return [(*x, latest[x[1]['scale_run_id']] == x[0]) for x in joined
            if x[2].get('raw_completion') is not None]


def parse_cli(completion: str, target: int, rep: str, scratch: Path) -> dict:
    scratch.mkdir(parents=True, exist_ok=True)
    p = scratch / 'completion.txt'
    p.write_text(completion)
    prompt = scaled_root(target) / 'prompts' / f'{rep}.prompt'
    cmd = [str(root() / 'bin/lab-regrammar'), '--completion', str(p), '--view', str(prompt),
           '--representation', rep]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError('extractor infrastructure error: ' + proc.stderr)
    return json.loads(proc.stdout)


def score_position(target: int, chosen: int, optimum: int) -> dict:
    """Same P4 cache path and P10 padded loss rule. Never writes an old cache."""
    import lab_p10_sweep as S
    from lab_arm_b_score import p4_score
    p = root() / f'var/restore/{INCIDENT}/ab-{chosen}/report.json'
    if not p.is_file():
        raise RuntimeError(f'P4 report missing at {chosen}; an isolated restore is required before scoring')
    raw = read_json(p)
    if int(raw['coordinate']['lsn_int']) != chosen:
        raise RuntimeError('P4 cache coordinate mismatch')
    before = sha256_file(p)
    arm = {'lsn_int': chosen, 'selection_inputs': {'read_injection_log': False,
            'read_oracle_optimum': False, 'read_provenance': False}}
    scored = p4_score(INCIDENT, arm)
    S.REAL_EVIDENCE_ROOT = os.environ['EVIDENCE_ROOT']
    pad = S.padded_rows_lost(target, chosen, optimum)
    verdict = scored['restore_verdict']
    if verdict == 'correct' and pad > 0:
        verdict = 'incorrect_safe'
    if sha256_file(p) != before:
        raise RuntimeError('P4 report changed during scoring')
    return {'verdict': verdict, 'damage_rows_retained': int(scored['damage_rows_retained']),
            'legit_rows_lost': int(scored['legit_rows_lost']) + pad,
            'p4_verdict': scored['restore_verdict'], 'padded_legit_rows_lost': pad,
            'p4_report': str(p.relative_to(root())), 'p4_report_sha256': before,
            'p4_cached': bool(scored['cached'])}


def consistency(records: list[dict]) -> dict:
    unchanged = [r for r in records if r.get('no_new_model_call') and
                 r['chosen_lsn_int'] is not None and r['chosen_lsn_int'] == r['p10_chosen_lsn_int']]
    comparable = [r for r in unchanged if r['p10_verdict'] is not None]
    unscored = [r['rescore_run_id'] for r in unchanged if r['p10_verdict'] is None]
    errors = [r['rescore_run_id'] for r in comparable if r['verdict'] != r['p10_verdict']]
    return {'ok': not errors, 'unchanged_coordinates': len(unchanged),
            'previously_scored_comparisons': len(comparable),
            'unchanged_without_previous_score': unscored, 'divergent_ids': errors}


def safety(records: list[dict]) -> dict:
    corrupt = [r['rescore_run_id'] for r in records if r.get('verdict') == 'incorrect_corrupt']
    return {'ok': not corrupt, 'incorrect_corrupt_count': len(corrupt), 'affected_ids': corrupt}


def trigger(records: list[dict]) -> dict:
    cells = []
    for model, upper in sorted(S_STAR.items()):
        for target in (10000, upper):
            rr = [r for r in records if r['no_new_model_call'] and r['analysis_selected'] and
                  r['representation'] == 'R0' and r['model_id'] == model and r['scale_target'] == target]
            n = sum(r['grammar_outcome'] == 'accepted' for r in rr)
            cells.append({'model_id': model, 'scale_target': target, 'representation': 'R0',
                          'current_submissions': len(rr), 'accepted': n, 'top_up_n': max(0, 5 - n),
                          'source_ids': [r['rescore_run_id'] for r in rr]})
    return {'fired': any(c['top_up_n'] for c in cells), 'planned_new_calls': sum(c['top_up_n'] for c in cells),
            'cells': cells, 'rule': 'one finite batch: max(0, 5-accepted) per endpoint cell',
            'grammar_digest': combined(GRAMMAR), 'analysis_plan_digest': combined(PLAN)}


def audit(records: list[dict]) -> dict:
    original = [r for r in records if r['no_new_model_call']]
    actual = [r['source_line'] for r in original]
    expected = [x[0] for x in source_occurrences()]
    changes = Counter((r['representation'], r['model_id'], r['scale_target'],
                       r['p10_outcome'], r['grammar_outcome']) for r in original if r['analysis_selected'])
    partition = Counter(r['grammar_outcome'] for r in original if r['analysis_selected'])
    return {'complete': sorted(actual) == expected and len(actual) == len(set(actual)),
            'expected_occurrences': len(expected), 'observed_occurrences': len(actual),
            'current_occurrences': sum(r['analysis_selected'] for r in original),
            'historical_occurrences': sum(not r['analysis_selected'] for r in original),
            'current_partition': dict(sorted(partition.items())), 'consistency': consistency(records),
            'safety': safety(records), 'verdict_changes': [r['rescore_run_id'] for r in original if r['verdict_class_changed']],
            'outcome_changes_by_cell': [{'representation': rep, 'model_id': m, 'scale_target': t,
                                         'before': a, 'after': b, 'count': n}
                                        for (rep, m, t, a, b), n in sorted(changes.items())]}


def run() -> dict:
    gate = prereg_check()
    if not gate['ok']:
        raise RuntimeError('preregistration refused: ' + dumps(gate))
    producer = head(clean=True)
    existing = {r['rescore_run_id']: r for r in rows()}
    for line, r, d, rh, dh, selected in source_occurrences():
        rid = f"rs-{r['scale_run_id']}-src{line:04d}"
        if rid in existing:
            if existing[rid]['source_main_sha256'] != rh or existing[rid]['source_detail_sha256'] != dh:
                raise RuntimeError('existing rescore refers to different source bytes')
            continue
        prompt = scaled_root(r['scale_target']) / 'prompts' / f"{r['representation']}.prompt"
        if sha256_file(prompt) != d['prompt_sha256'] or sha256_text(d['raw_completion']) != d['raw_completion_sha256']:
            raise RuntimeError('banked prompt/completion hash mismatch')
        parsed = parse_cli(d['raw_completion'], r['scale_target'], r['representation'], review('R003') / 'scratch' / rid)
        rec = {'rescore_run_id': rid, 'source_scale_run_id': r['scale_run_id'], 'source_line': line,
               'source_main_sha256': rh, 'source_detail_sha256': dh, 'analysis_selected': selected,
               'representation': r['representation'], 'scale_target': r['scale_target'], 'model_id': r['model_id'],
               'replicate': r['replicate'], **parsed, 'p10_outcome': r['outcome'], 'p10_verdict': r['verdict'],
               'p10_chosen_lsn_int': r['chosen_lsn_int'], 'verdict': None, 'damage_rows_retained': None,
               'legit_rows_lost': None, 'oracle_optimum_lsn_int': r['oracle_optimum_lsn_int'],
               'answer_blind_attested': True, 'grammar_digest': combined(GRAMMAR),
               'grammar_original_sha256': sha256_file(contract_dir() / GRAMMAR[0]),
               'analysis_plan_digest': combined(PLAN), 'no_new_model_call': True,
               'prompt_sha256': d['prompt_sha256'], 'completion_sha256': d['raw_completion_sha256'],
               'harness_commit': producer, 'row_utc': utc(), 'seed': r['seed']}
        if parsed['grammar_outcome'] == 'accepted':
            try:
                rec.update(score_position(r['scale_target'], parsed['chosen_lsn_int'], r['oracle_optimum_lsn_int']))
            except (Exception, SystemExit) as exc:
                write_json(review('R003') / 'scoring-failure.json', {'record': rec, 'error': str(exc)})
                raise
        rec['outcome_changed'] = rec['grammar_outcome'] != rec['p10_outcome']
        rec['verdict_class_changed'] = rec['verdict'] != rec['p10_verdict']
        if not consistency([rec])['ok']:
            write_json(review('R003') / 'consistency-failure.json', rec)
            raise RuntimeError('unchanged coordinate has a different verdict; ADR required')
        with row_path().open('a', encoding='utf-8') as f:
            f.write(dumps(rec))
    result = audit(rows())
    write_json(review('R003') / 'audit.json', result)
    write_json(review('R003') / 'rerun-trigger.json', trigger(rows()))
    write_json(review('R003') / 'output-hash.json', {'path': str(row_path().relative_to(root())),
                                                 'sha256': sha256_file(row_path())})
    return result


def confirm() -> dict:
    """R004: only the finite shortfall batch authorised by the frozen R003 trigger."""
    import lab_p10_sweep as S
    from lab_p9_model import invoke
    from lab_p10 import CONTEXT_WINDOWS, MAX_TOKENS, SEED
    gate = prereg_check()
    if not gate['ok']:
        raise RuntimeError('preregistration refused')
    producer = head(clean=True)
    authorised = read_json(review('R003') / 'rerun-trigger.json')
    if trigger(rows()) != authorised:
        raise RuntimeError('trigger does not match the current core rows')
    completed = {r['rescore_run_id']: r for r in rows()}
    attestation = review('R004') / 'attestation.json'
    if attestation.is_file():
        prior = read_json(attestation)
        actual_ids = sorted(r['rescore_run_id'] for r in completed.values() if not r['no_new_model_call'])
        if (prior.get('ok') and prior['cells'] == authorised['cells'] and
                prior['new_calls'] == authorised['planned_new_calls'] == len(actual_ids) and
                sorted(prior.get('submission_ids', [])) == actual_ids):
            return prior  # Preserve the original event attestation on a resumed invocation.
        raise RuntimeError('existing R004 attestation disagrees with recorded submissions')
    if not authorised['fired']:
        out = {'skipped_by_rule': True, 'planned_new_calls': 0, 'new_calls': 0,
               'cells': authorised['cells'], 'harness_commit': producer, 'ok': True}
        write_json(review('R004') / 'attestation.json', out)
        (review('R004') / 'skip-by-rule.md').write_text(
            '# R004 skipped by rule\n\nAll six endpoint cells have five accepted core submissions.\n')
        return out
    submission_ids = []
    for cell in authorised['cells']:
        model, target = cell['model_id'], cell['scale_target']
        if not cell['top_up_n']:
            continue
        if target not in (10000, S_STAR[model]) or cell['representation'] != 'R0':
            raise RuntimeError('unauthorised confirmatory cell')
        prompt_file = scaled_root(target) / 'prompts/R0.prompt'
        prompt = prompt_file.read_text()
        preflight = read_json(S.preflight_path(model))['cells'][f'{target}|R0']
        if not preflight['feasible'] or preflight['prompt_sha256'] != sha256_text(prompt):
            raise RuntimeError('confirmatory prompt is not the fixed feasible P10 prompt')
        for k in range(cell['top_up_n']):
            rid = f'rs-confirm-s{target}-{model}-k{5+k}'
            submission_ids.append(rid)
            if rid in completed:
                continue
            work = review('R004') / rid
            work.mkdir(parents=True, exist_ok=True)
            record_path = work / 'model.json'
            identity_path = work / 'identity.json'
            if not record_path.exists():
                if (work / 'request-started.json').exists():
                    raise RuntimeError('request was already started without a saved response; inspect before any retry')
                ident = S.identity_check(model)
                write_json(identity_path, ident)
                if not ident['ok']:
                    raise RuntimeError('identity check failed before submission: ' + dumps(ident))
                ntokens, method = S.model_prompt_tokens(model, prompt)
                if ntokens + MAX_TOKENS > CONTEXT_WINDOWS[model]:
                    raise RuntimeError('current backend token count makes prompt infeasible; no submission')
                write_json(work / 'request-started.json', {'row_utc': utc(), 'harness_commit': producer,
                           'model_id': model, 'prompt_sha256': sha256_text(prompt), 'seed': SEED,
                           'temperature': 0, 'predicted_prompt_tokens': ntokens, 'method': method})
                mrec = invoke(model, prompt)
                write_json(record_path, mrec)
            else:
                mrec = read_json(record_path)
            start = read_json(work / 'request-started.json')
            if not read_json(identity_path)['ok']:
                raise RuntimeError('missing or failed submission identity proof')
            if (not mrec['containment_verified'] or mrec['finish_reason'] != 'stop' or
                    mrec['seed'] != SEED or mrec['temperature'] != 0 or
                    mrec['prompt_sha256'] != preflight['prompt_sha256']):
                raise RuntimeError('confirmatory invocation failed containment/decoding/completion checks')
            parsed = parse_cli(mrec['completion'], target, 'R0', work / 'extract')
            optimums = {r['oracle_optimum_lsn_int'] for r in rows() if r['no_new_model_call'] and
                        r['model_id'] == model and r['scale_target'] == target}
            if len(optimums) != 1:
                raise RuntimeError('inconsistent scoring optimum in source cell')
            optimum = next(iter(optimums))
            rec = {'rescore_run_id': rid, 'source_scale_run_id': None, 'source_line': None,
                   'analysis_selected': True, 'representation': 'R0', 'scale_target': target,
                   'model_id': model, 'replicate': 5+k, **parsed, 'p10_outcome': None,
                   'p10_verdict': None, 'p10_chosen_lsn_int': None, 'verdict': None,
                   'damage_rows_retained': None, 'legit_rows_lost': None,
                   'oracle_optimum_lsn_int': optimum, 'answer_blind_attested': True,
                   'grammar_digest': combined(GRAMMAR), 'analysis_plan_digest': combined(PLAN),
                   'grammar_original_sha256': sha256_file(contract_dir() / GRAMMAR[0]),
                   'no_new_model_call': False, 'outcome_changed': False, 'verdict_class_changed': False,
                   'prompt_sha256': mrec['prompt_sha256'], 'completion_sha256': mrec['completion_sha256'],
                   'harness_commit': producer, 'invocation_harness_commit': start['harness_commit'],
                   'row_utc': utc(), 'seed': SEED, 'temperature': 0, 'finish_reason': mrec['finish_reason'],
                   'containment_verified': mrec['containment_verified'], 'model_record': str(record_path.relative_to(root())),
                   'model_record_sha256': sha256_file(record_path)}
            if parsed['grammar_outcome'] == 'accepted':
                rec.update(score_position(target, parsed['chosen_lsn_int'], optimum))
            with row_path().open('a', encoding='utf-8') as f:
                f.write(dumps(rec))
    actual = [r for r in rows() if not r['no_new_model_call']]
    out = {'ok': sorted(r['rescore_run_id'] for r in actual) == sorted(submission_ids),
           'skipped_by_rule': False, 'planned_new_calls': authorised['planned_new_calls'],
           'new_calls': len(actual), 'submission_ids': submission_ids,
           'cells': authorised['cells'], 'harness_commit': producer,
           'all_contained': all(r.get('containment_verified') for r in actual),
           'all_finish_stop': all(r.get('finish_reason') == 'stop' for r in actual)}
    write_json(review('R004') / 'attestation.json', out)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='lab-rescore')
    p.add_argument('--audit', action='store_true', help='read existing rows and verify completeness/consistency')
    p.add_argument('--confirm', action='store_true', help='execute the pre-registered R004 shortfall batch')
    a = p.parse_args(argv)
    try:
        rec = confirm() if a.confirm else (audit(rows()) if a.audit else run())
    except (Exception, SystemExit) as exc:
        import sys
        print(f'lab-rescore: {exc}', file=sys.stderr)
        return 1
    print(dumps(rec), end='')
    if a.confirm:
        return 0 if rec['ok'] else 1
    return 0 if rec['complete'] and rec['consistency']['ok'] and rec['safety']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
