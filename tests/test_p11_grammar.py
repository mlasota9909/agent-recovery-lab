"""P11 external boundary tests; synthetic evidence only, no banked answers."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from lab_p11 import dumps, review, root, write_json
from lab_regrammar import extract

CONTENT = '\n'.join([
    json.dumps({'lsn_int': 100, 'lsn_text': '0/64', 'xid': 1, 'natural_key': 'a',
                'commit_lsn': 110, 'commit_ts': '2026-01-01T00:00:01.100Z'}),
    json.dumps({'lsn_int': 200, 'xid': 2, 'natural_key': 'b',
                'commit_lsn': 210, 'commit_ts': '2026-01-01T00:00:02.100Z'}),
    json.dumps({'lsn_int': 220, 'xid': 2, 'natural_key': 'b',
                'commit_lsn': 230, 'commit_ts': '2026-01-01T00:00:02.900Z'}),
    'Window 14 [300..399]: synthetic.', 'Window 15 [400..499]: synthetic.'
])
CASES = [
    ('COORDINATE: lsn=0/64 lsn=100', 'accepted', 100),
    ('COORDINATE: lsn_int=100 lsn_hex=0/64', 'accepted', 100),
    ('COORDINATE: lsn=100 lsn=200', 'refusal_parser', None),
    ('COORDINATE: lsn=100 lsn=999999', 'accepted', 100),
    ('COORDINATE: lsn=999999', 'refusal_parser', None),
    ('COORDINATE: ts=2026-01-01T00:00:01.999Z', 'accepted', 110),
    ('COORDINATE: ts=2026-01-01T00:00:02Z', 'refusal_parser', None),
    ('COORDINATE: lsn=100 ts=2026-01-01T00:00:59Z', 'accepted', 100),
    ('COORDINATE: lsn=100 ts=2026-01-01T00:00:01Z', 'refusal_parser', None),
    ('COORDINATE: event_ref=xid:1 row=a', 'accepted', 110),
    ('COORDINATE: xid=2', 'refusal_parser', None),
    ('COORDINATE: window=15', 'accepted', 399),
    ('COORDINATE: window=14', 'refusal_parser', None),
    ('COORDINATE: lsn=100 bad-token', 'accepted', 100),
    ('COORDINATE: lsn=-100', 'refusal_parser', None),
    ('COORDINATE: lsn=100\nCOORDINATE: lsn=100', 'refusal_parser', None),
    ('REFUSAL: evidence missing\nREFUSAL: cannot choose', 'refusal_genuine', None),
    ('COORDINATE: lsn=100\nREFUSAL: cannot choose', 'refusal_parser', None),
    ('No tagged line.', 'refusal_parser', None),
]


class ReadGuard(dict):
    """An external tainted mapping. Forbidden-key access fails even if unused later."""
    def __init__(self, data, allowed):
        super().__init__(data)
        self.allowed, self.reads = allowed, []

    def __getitem__(self, key):
        self.reads.append(key)
        if key not in self.allowed:
            raise AssertionError('forbidden input read: ' + str(key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key not in self.allowed or key in self:
            return self[key]
        return default

    def items(self):
        return [(k, self[k]) for k in dict.keys(self)]

    def values(self):
        return [self[k] for k in dict.keys(self)]


def blind_guard(fn):
    answers, reads = [], []
    for present in (False, True):
        data = {'completion': 'COORDINATE: lsn=100 lsn=200', 'content': CONTENT}
        if present:
            data.update(oracle_optimum_lsn_int=100, principal='tainted', injection_log={'lsn': 100})
        inp = ReadGuard(data, {'completion', 'content', 'representation'})
        envdata = dict(os.environ)
        if present:
            envdata['ORACLE_OPTIMUM_LSN_INT'] = '100'
        env = ReadGuard(envdata, {k for k in envdata if not any(x in k.lower() for x in ('oracle', 'principal', 'injection'))})
        with patch.object(os, 'environ', env):
            answers.append(dumps(fn(inp)))
        reads.append({'inputs': inp.reads, 'environment': env.reads})
    if answers[0] != answers[1]:
        raise AssertionError('oracle changed parse')
    return {'identical': True, 'reads': reads, 'oracle_value_read': False}


def parity_guard(fn):
    for completion, _, _ in CASES:
        rr = [dumps(fn({'completion': completion, 'content': CONTENT, 'representation': r}))
              for r in ('R0', 'R2')]
        if rr[0] != rr[1]:
            raise AssertionError('representation label changed the parse')
    return {'same_content_cases': len(CASES), 'identical': True}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=review('R002') / 'grammar-checks.json')
    a = p.parse_args(argv)
    scratch = a.out.parent / 'scratch/grammar'
    scratch.mkdir(parents=True, exist_ok=True)
    view, completion = scratch / 'view.txt', scratch / 'completion.txt'
    view.write_text(CONTENT)
    command = [str(root() / 'bin/lab-regrammar'), '--completion', str(completion), '--view', str(view)]
    cases = []
    for text, expected, position in CASES:
        completion.write_text(text)
        first = subprocess.run(command + ['--representation', 'R0'], text=True, capture_output=True)
        second = subprocess.run(command + ['--representation', 'R2'], text=True, capture_output=True)
        assert first.returncode == second.returncode == 0, first.stderr + second.stderr
        parsed = json.loads(first.stdout)
        assert first.stdout == second.stdout
        assert (parsed['grammar_outcome'], parsed['chosen_lsn_int']) == (expected, position), parsed
        assert first.stdout == dumps(extract({'completion': text, 'content': CONTENT}))
        cases.append({'completion': text, 'expected': expected, 'position': position,
                      'cli_outputs_identical': True})
    no_commit = json.dumps({'lsn_int': 100, 'wall_clock': '2026-01-01T00:00:01Z'})
    assert extract({'completion': 'COORDINATE: ts=2026-01-01T00:00:01Z', 'content': no_commit})['grammar_outcome'] == 'refusal_parser'
    assert extract({'completion': 'COORDINATE: window=0', 'content': 'Window 0 [100..200]'})['chosen_lsn_int'] == 99
    blind = blind_guard(extract)
    parity = parity_guard(extract)

    def oracle_mutant(inp):
        rec = extract(inp)
        optimum = inp['oracle_optimum_lsn_int']
        rec['chosen_lsn_int'] = min(rec['locators_resolved_to'], key=lambda n: abs(n - optimum))
        return rec

    def environment_mutant(inp):
        rec = extract(inp)
        rec['chosen_lsn_int'] = int(os.environ.get('ORACLE_OPTIMUM_LSN_INT', '100'))
        return rec

    def representation_mutant(inp):
        rec = extract(inp)
        if inp['representation'] == 'R0':
            rec['grammar_outcome'] = 'accepted'
        return rec

    negatives = []
    for name, guard, mutant in [('nearest-oracle', blind_guard, oracle_mutant),
                               ('oracle-environment', blind_guard, environment_mutant),
                               ('representation-branch', parity_guard, representation_mutant)]:
        try:
            guard(mutant)
        except AssertionError as exc:
            negatives.append({'mutant': name, 'rejected': True, 'reason': str(exc)})
        else:
            raise AssertionError(name + ' escaped guard')
    report = {'ok': True, 'commands': [command], 'cases': cases, 'answer_blind': blind,
              'symmetry': parity, 'negative_tests': negatives, 'synthetic_evidence_only': True}
    write_json(a.out, report)
    print(json.dumps({'ok': True, 'cases': len(cases) + 2, 'mutants_rejected': len(negatives)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
