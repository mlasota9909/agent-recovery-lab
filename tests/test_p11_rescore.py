"""R003 mechanical replay and external negative cases, using the real CLI/P4 scorer."""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from lab_p10 import INCIDENT, scaled_root, sha256_file, sha256_text
from lab_p11 import review, root, rows, write_json
from lab_p11_rescore import audit, consistency, parse_cli, safety, score_position, source_occurrences, trigger


def main(argv=None):
    required = root() / 'results/scaling-runs.jsonl'
    if not required.is_file():
        print(json.dumps({"ok": True, "skipped": "needs the development repository's P10/P11 records: " + str(required.relative_to(root()))}))
        return 0
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=review('R003') / 'checks.json')
    a = p.parse_args(argv)
    scratch = a.out.parent / 'scratch/verification'
    scratch.mkdir(parents=True, exist_ok=True)
    recorded = rows()
    by_line = {r['source_line']: r for r in recorded if r['no_new_model_call']}
    checked = []
    for line, old, detail, rh, dh, selected in source_occurrences():
        row = by_line[line]
        parsed = parse_cli(detail['raw_completion'], old['scale_target'], old['representation'], scratch)
        assert all(row[k] == v for k, v in parsed.items()), row['rescore_run_id']
        assert row['source_main_sha256'] == rh and row['source_detail_sha256'] == dh
        assert row['analysis_selected'] == selected
        assert row['p10_verdict'] == old['verdict'] and row['p10_outcome'] == old['outcome']
        assert row['p10_chosen_lsn_int'] == old['chosen_lsn_int']
        assert row['completion_sha256'] == sha256_text(detail['raw_completion'])
        prompt = scaled_root(old['scale_target']) / 'prompts' / f"{old['representation']}.prompt"
        assert row['prompt_sha256'] == sha256_file(prompt)
        if parsed['grammar_outcome'] == 'accepted':
            score = score_position(old['scale_target'], parsed['chosen_lsn_int'], old['oracle_optimum_lsn_int'])
            assert all(row[k] == v for k, v in score.items()), row['rescore_run_id']
        else:
            assert row['verdict'] is None
        checked.append(row['rescore_run_id'])
    result = audit(recorded)
    assert result['complete'] and result['consistency']['ok']

    original = next(r for r in recorded if r['p10_verdict'] is not None and
                    r['chosen_lsn_int'] == r['p10_chosen_lsn_int'])
    bad = dict(original, verdict='incorrect_corrupt')
    if bad['verdict'] == original['verdict']:
        bad['verdict'] = 'correct'
    write_json(scratch / 'flipped-verdict.json', bad)
    flipped = consistency([bad])
    assert not flipped['ok']

    # Real P4 damage-retaining restore report, copied unchanged into a scratch
    # cache. Its proven coordinate is offered in synthetic visible evidence.
    # Patch only cache LOCATION outside the scorer, never its scoring logic.
    import lab_arm_b_score as P4
    from lab_regrammar import extract
    source = root() / f'var/restore/{INCIDENT}/too_late_naive/report.json'
    real = json.loads(source.read_text())
    position = real['coordinate']['lsn_int']
    dest = scratch / f'ab-{position}'
    dest.mkdir(exist_ok=True)
    shutil.copy2(source, dest / 'report.json')
    chosen = extract({'completion': f'COORDINATE: lsn={position}',
                      'content': json.dumps({'lsn_int': position})})
    assert chosen['grammar_outcome'] == 'accepted'
    with patch.object(P4, 'restore_root', lambda incident, tag: scratch / tag):
        scored = P4.p4_score(INCIDENT, {'lsn_int': chosen['chosen_lsn_int'],
                                      'selection_inputs': {'read_injection_log': False,
                                        'read_oracle_optimum': False, 'read_provenance': False}})
    unsafe = {'rescore_run_id': 'synthetic-damage', 'verdict': scored['restore_verdict']}
    flagged = safety([unsafe])
    assert scored['restore_verdict'] == 'incorrect_corrupt' and not flagged['ok']
    report = {'ok': True, 'rederived_occurrences': len(checked), 'audit': result,
              'trigger': trigger(recorded), 'negative_flipped_verdict': flipped,
              'negative_corrupt': {'source_report_sha256': sha256_file(source), 'chosen_lsn_int': position,
                                   'verdict': scored['restore_verdict'],
                                   'damage_rows_retained': scored['damage_rows_retained'], 'safety': flagged}}
    write_json(a.out, report)
    print(json.dumps({'ok': True, 'rederived': len(checked), 'negatives_caught': 2,
                      'actual_safety_ok': result['safety']['ok']}))
    return 0 if result['safety']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
