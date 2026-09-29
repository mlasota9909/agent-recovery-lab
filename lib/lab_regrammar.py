"""Frozen P11 locator grammar. No scorer, archive, oracle or model import."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LSN = re.compile(r'(?:[0-9A-Fa-f]+/[0-9A-Fa-f]+|[0-9]+)\Z')
WINDOW = re.compile(r'Window\s+(-?\d+)\s+\[(\d+)\.\.(\d+)\]')


def number(value) -> int:
    if isinstance(value, bool) or not LSN.fullmatch(str(value)):
        raise ValueError('invalid LSN')
    text = str(value)
    if '/' in text:
        hi, lo = text.split('/')
        if int(hi, 16) > 0xffffffff or int(lo, 16) > 0xffffffff:
            raise ValueError('LSN exceeds 64 bits')
        return (int(hi, 16) << 32) + int(lo, 16)
    result = int(text)
    if not 0 <= result < 2**64:
        raise ValueError('LSN exceeds 64 bits')
    return result


def second(value: str) -> int:
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('timestamp needs UTC offset')
    return int(t.astimezone(timezone.utc).timestamp() // 1)


def visible_index(content: str) -> dict:
    """Only allowlisted model-visible fields enter the locator index."""
    positions, windows, commits, refs = set(), {}, {}, {}
    for line in content.splitlines():
        line = line.strip()
        wm = WINDOW.match(line)
        if wm:
            wid, lo, hi = map(int, wm.groups())
            if lo > hi or min(lo, hi) < 0:
                raise ValueError('invalid visible window range')
            pair = (lo, hi)
            if wid in windows and windows[wid] != pair:
                raise ValueError('conflicting visible window definitions')
            windows[wid] = pair
            positions.update(pair)
            continue
        if not line.startswith('{'):
            continue
        ev = json.loads(line)
        change = [number(ev[k]) for k in ('lsn_int', 'lsn_text') if k in ev]
        if len(set(change)) > 1:
            raise ValueError('inconsistent LSN spellings in the view')
        commit = number(ev['commit_lsn']) if 'commit_lsn' in ev else None
        positions.update(change)
        if commit is not None:
            positions.add(commit)
            if 'commit_ts' in ev:
                commits.setdefault(second(ev['commit_ts']), set()).add(commit)
        position = commit if commit is not None else (change[0] if change else None)
        if position is not None:
            for source, kind in (('xid', 'xid'), ('natural_key', 'row')):
                if source in ev:
                    refs.setdefault((kind, str(ev[source])), set()).add(position)
    return {'positions': positions, 'windows': windows, 'commits': commits, 'refs': refs}


def resolve(token: str, index: dict) -> dict:
    out = {'token': token, 'type': 'unknown', 'resolved_lsn_int': None, 'discard_reason': None}
    if '=' not in token:
        out['discard_reason'] = 'malformed locator: expected key=value'
        return out
    key, value = token.split('=', 1)
    try:
        if key in ('lsn', 'lsn_int', 'lsn_hex'):
            out['type'] = 'lsn_hex' if '/' in value else 'lsn_int'
            n = number(value)
            if n not in index['positions']:
                raise ValueError('position not present in the visible evidence')
        elif key == 'ts':
            out['type'] = 'ts'
            matches = index['commits'].get(second(value), set())
            if not matches:
                raise ValueError('no explicit visible commit in this UTC second')
            if len(matches) != 1:
                raise ValueError('multiple explicit visible commits in this UTC second')
            n = next(iter(matches))
        elif key == 'window':
            out['type'] = 'window'
            wid = int(value)
            if wid not in index['windows']:
                raise ValueError('named window is not visible')
            if wid == 0:
                n = index['windows'][0][0] - 1
                if n < 0:
                    raise ValueError('window 0 has no preceding position')
            elif wid - 1 in index['windows']:
                n = index['windows'][wid - 1][1]
            else:
                raise ValueError('immediately preceding window is not visible')
        elif key in ('event_ref', 'xid', 'row'):
            out['type'] = 'event_ref'
            if key == 'event_ref':
                kind, ident = value.split(':', 1)
            else:
                kind, ident = key, value
            if kind not in ('xid', 'row'):
                raise ValueError('unknown event reference kind')
            if kind == 'xid':
                ident = str(int(ident))
            matches = index['refs'].get((kind, ident), set())
            if len(matches) != 1:
                raise ValueError('event reference missing or identifies multiple visible positions')
            n = next(iter(matches))
        else:
            raise ValueError('unrecognised locator key')
        out['resolved_lsn_int'] = n
    except (ValueError, TypeError, OverflowError) as exc:
        out['discard_reason'] = str(exc)
    return out


def extract(inputs) -> dict:
    """The sole semantic input reads are completion and content. No representation branch."""
    completion, content = inputs['completion'], inputs['content']
    if not isinstance(completion, str) or not isinstance(content, str):
        raise ValueError('completion and content must be text')
    coords, refusals = [], []
    for line in completion.splitlines():
        text = line.strip()
        if text.startswith('COORDINATE:'):
            coords.append(text[len('COORDINATE:'):].strip())
        elif text.startswith('REFUSAL:'):
            refusals.append(text[len('REFUSAL:'):].strip())
    rec = {'grammar_outcome': 'refusal_parser', 'chosen_lsn_int': None,
           'locators_offered': [], 'locators_resolved_to': [], 'locators': [], 'reason': ''}
    if refusals and not coords:
        rec.update(grammar_outcome='refusal_genuine', reason='declared refusal without coordinate')
        return rec
    if len(coords) != 1 or refusals:
        rec['reason'] = 'expected exactly one coordinate line and no refusal line'
        return rec
    index = visible_index(content)
    locators = [resolve(token, index) for token in coords[0].split()]
    resolved = [x['resolved_lsn_int'] for x in locators if x['resolved_lsn_int'] is not None]
    rec.update(locators=locators, locators_offered=[x['type'] for x in locators],
               locators_resolved_to=resolved)
    if not resolved:
        rec['reason'] = 'no locator resolves from the supplied view'
    elif len(set(resolved)) != 1:
        rec['reason'] = 'resolved locators identify distinct positions'
    else:
        rec.update(grammar_outcome='accepted', chosen_lsn_int=resolved[0],
                   reason='all resolved locators agree')
    return rec


def content_from_text(text: str) -> str:
    if '<<<ARM_B_CONTENT' in text:
        if text.count('<<<ARM_B_CONTENT') != 1 or text.count('ARM_B_CONTENT>>>') != 1:
            raise ValueError('ambiguous prompt content boundaries')
        return text.split('<<<ARM_B_CONTENT', 1)[1].split('ARM_B_CONTENT>>>', 1)[0]
    if text.lstrip().startswith('{'):
        try:
            view = json.loads(text)
        except json.JSONDecodeError:
            return text  # JSON lines view
        if isinstance(view, dict) and 'content' in view:
            return view['content']
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='lab-regrammar')
    p.add_argument('--completion', type=Path, required=True)
    p.add_argument('--view', type=Path, required=True, help='frozen prompt, model-view JSON or visible content')
    p.add_argument('--representation', choices=('R0', 'R2'), help='label only; never used for extraction')
    a = p.parse_args(argv)
    try:
        rec = extract({'completion': a.completion.read_text(),
                       'content': content_from_text(a.view.read_text())})
    except (OSError, ValueError, TypeError) as exc:
        print(f'lab-regrammar: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(rec, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
