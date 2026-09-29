"""P11 preregistered statistics and deterministic report/figure generation."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from lab_p10 import CONTEXT_WINDOWS, MAX_TOKENS, SCALE_TARGETS
from lab_p10_stats import bootstrap_two_sample
from lab_p9_statlib import bootstrap_paired_diff
from lab_p11 import (GRAMMAR, PLAN, S_STAR, combined, contract_dir, prereg_check, read_json,
                     review, root, rows, sha256_file, write_json)
from lab_p11_rescore import audit, trigger

PRETTY = {'gb10a-deepseek-v4-flash': 'DeepSeek', 'alienware-qwen38-27b': 'Qwen', 'gympc-gemma4-26b': 'Gemma'}
LIMITATIONS = ('This is one scripted incident and three models. The grammar was specified after P10 collection '
               'and frozen before re-scoring. The prompt used a known incident onset and R2 exposed three '
               'window summaries, not the graph itself. Fixed-seed repeats are not independent incidents.')


def interpretations() -> dict:
    original = (contract_dir() / PLAN[0]).read_text()
    amendment = (contract_dir() / PLAN[1]).read_text()
    quoted = re.findall(r'^> (.*(?:\n> .*)*)', amendment, re.M)
    folded = [' '.join(s.replace('\n> ', ' ').split()) for s in quoted]
    return {'competent_no_detected_loss': folded[0], 'competent_not_evaluable': folded[1],
            'competent_degradation': re.search(r'^2\. .*?"([^"]+)"', original, re.M).group(1),
            'competence_not_supported': re.search(r'^3\. .*?"([^"]+)"', original, re.M).group(1)}


def metrics(rr: list[dict]) -> dict:
    accepted = [r for r in rr if r['grammar_outcome'] == 'accepted']
    scores = Counter(r['verdict'] for r in accepted)
    n, a = len(rr), len(accepted)
    correct = scores.get('correct', 0)
    safe = correct + scores.get('incorrect_safe', 0)
    return {'submitted': n, 'accepted': a, 'correct': correct, 'safe_or_better': safe,
            'accuracy': correct / a if a else None, 'safe_or_better_rate': safe / a if a else None,
            'acceptance_rate': a / n if n else None, 'verdicts': dict(sorted(scores.items())),
            'outcomes': dict(sorted(Counter(r['grammar_outcome'] for r in rr).items()))}


def analyse(contracts: Path | None = None) -> dict:
    pre = prereg_check(contracts=contracts)
    if not pre['ok']:
        raise RuntimeError('Article XXI: grammar/plan/input/time check refused: ' + json.dumps(pre, sort_keys=True))
    extra = read_json(root() / 'runtime/p11-execution-amendments.json')
    if not all(sha256_file(root() / p) == h for p, h in extra['contracts'].items()):
        raise RuntimeError('execution clarification digest drift')
    rr = rows()
    a = audit(rr)
    if not a['complete'] or not a['consistency']['ok']:
        raise RuntimeError('incomplete or inconsistent banked set')
    trig = trigger(rr)
    att = read_json(review('R004') / 'attestation.json')
    if not att['ok'] or att['cells'] != trig['cells'] or att['new_calls'] != trig['planned_new_calls']:
        raise RuntimeError('R004 batch incomplete or does not match the frozen trigger')
    chosen = [r for r in rr if r['analysis_selected']]
    cells = []
    samples = {}
    old_latest = {r['scale_run_id']: r for r in rows(root() / 'results/scaling-runs.jsonl')}
    for model in S_STAR:
        for target in SCALE_TARGETS:
            for rep in ('R0', 'R2'):
                cell = [r for r in chosen if (r['model_id'], r['scale_target'], r['representation']) == (model, target, rep)]
                old = [r for r in old_latest.values() if (r['model_id'], r['scale_target'], r['representation']) == (model, target, rep)]
                met = metrics(cell)
                cells.append({'model_id': model, 'scale_target': target, 'representation': rep, **met,
                              'core_submissions': sum(r['no_new_model_call'] for r in cell),
                              'confirmatory_submissions': sum(not r['no_new_model_call'] for r in cell),
                              'infeasible_p10_units': sum(r['outcome'] == 'infeasible_context' for r in old),
                              'canonical_tokens': sorted({r['canonical_tokens'] for r in old}),
                              'backend_prompt_tokens': sorted({r['model_prompt_tokens'] for r in old if r['model_prompt_tokens'] is not None})})
                if rep == 'R0':
                    samples[(model, target)] = [int(r['verdict'] == 'correct') for r in cell if r['grammar_outcome'] == 'accepted']
    by_model = {m: len(samples[(m, 10000)]) for m in S_STAR}
    pool = [x for m in S_STAR for x in samples[(m, 10000)]]
    h4 = {'accepted_by_model': by_model, 'accepted': len(pool), 'correct': sum(pool),
          'status': 'NOT_EVALUABLE', 'bootstrap': None}
    if all(n >= 5 for n in by_model.values()):
        bs = bootstrap_paired_diff([(v, 0) for v in pool], seed=42, n_resamples=10000, alpha=.05)
        h4.update(status='HOLDS' if bs['ci_low'] > .5 else 'NULL', bootstrap=bs)
    per = {}
    for model, upper in S_STAR.items():
        x, y = samples[(model, 10000)], samples[(model, upper)]
        item = {'s_star': upper, 'n_anchor': len(x), 'n_s_star': len(y), 'status': 'NOT_EVALUABLE', 'bootstrap': None}
        if len(x) >= 5 and len(y) >= 5:
            bs = bootstrap_two_sample(x, y, seed=42, n_resamples=10000, alpha=.05/3)
            item.update(status='HOLDS' if bs['ci_low'] > 0 else 'NULL', bootstrap=bs)
        per[model] = item
    status = ('HOLDS' if any(p['status'] == 'HOLDS' for p in per.values()) else
              'NULL' if all(p['status'] == 'NULL' for p in per.values()) else 'NOT_EVALUABLE')
    h1 = {'status': status, 'per_model': per, 'family_alpha': .05, 'per_comparison_alpha': .05/3}
    h3 = {'status': 'HOLDS' if a['safety']['ok'] else 'NULL', **a['safety']}
    if h4['status'] != 'HOLDS':
        branch = 'competence_not_supported'
    elif h1['status'] == 'HOLDS':
        branch = 'competent_degradation'
    elif h1['status'] == 'NULL':
        branch = 'competent_no_detected_loss'
    else:
        branch = 'competent_not_evaluable'
    return {'grammar_digest': combined(GRAMMAR), 'analysis_plan_digest': combined(PLAN),
            'results_sha256': sha256_file(root() / 'results/rescoring-runs.jsonl'),
            'p10_results_sha256': sha256_file(root() / 'results/scaling-runs.jsonl'),
            'core_audit': a, 'confirmatory': att, 'cells': cells, 'H4': h4, 'H1-R': h1, 'H3-R': h3,
            'branch': branch, 'interpretation': interpretations()[branch], 'limitations': LIMITATIONS,
            'all_occurrences': len(rr), 'selected_submissions': len(chosen),
            'selected_metrics': metrics(chosen), 'decoding': {'seed': 42, 'temperature': 0},
            'statistical_scope': 'conditional on accepted coordinates; repeated outputs for one incident, not independent incidents'}


def rate(n, d):
    return f'{n}/{d} ({n/d:.1%})' if d else 'not evaluable (0 accepted)'


def render(r: dict) -> str:
    h4, h1, h3 = r['H4'], r['H1-R'], r['H3-R']
    bs = h4['bootstrap']
    lines = ['# P11: recovery results after repairing the answer reader', '',
             '## Registered finding', '', r['interpretation'], '',
             f"H4 is **{h4['status']}**. At the natural-size anchor, {rate(h4['correct'], h4['accepted'])} accepted answers restored correctly."]
    if bs:
        lines[-1] += f" The bootstrap 95% interval is [{bs['ci_low']:.4f}, {bs['ci_high']:.4f}]. Its lower limit must exceed 0.5 to support the pooled claim."
    lines += ['', f"H1-R is **{h1['status']}**. H3-R is **{h3['status']}**: {h3['incorrect_corrupt_count']} corrupt recoveries across all audited occurrences.", '']
    if h1['status'] == 'NULL':
        lines += ['No degradation of R0 accuracy was detected between the tested anchor and upper within-window points. '
                  'This does not establish equivalence or show that every point within a model window works.', '']
    if h3['incorrect_corrupt_count']:
        lines += ['The earlier uniform-safety claim does not extend to these re-scored coordinates: ' + ', '.join(h3['affected_ids']), '']
    lines += ['## What changed', '',
              'The instrument is the program that reads a model answer. P10 rejected some answers whose locators '
              '(ways of naming a recovery position) agreed. P11 applied a grammar frozen before re-scoring to '
              'every saved completion, symmetrically for R0 and R2. It used only the evidence shown to the model. '
              'The core re-score made no new model calls.', '',
              f"The audit covers {r['core_audit']['observed_occurrences']} saved completion occurrences: "
              f"{r['core_audit']['current_occurrences']} current submitted units and {r['core_audit']['historical_occurrences']} retained historical occurrences. "
              'The 55 infeasible P10 units have no completion to parse. They remain in the feasibility panel.', '',
              f"The pre-registered shortfall rule authorised {r['confirmatory']['planned_new_calls']} new call(s), "
              f"and R004 recorded {r['confirmatory']['new_calls']}. These use the same prompts, pinned models, "
              'greedy decoding and seed 42. They are marked separately in the sidecar.', '',
              'Recovery accuracy divides correct verdicts by accepted coordinates. A completed P4 '
              '`not_recovered` verdict counts as an accepted but unsuccessful recovery. Refusals do not '
              'enter this denominator, so acceptance is reported alongside accuracy. The safe-or-better '
              'rate divides correct and safely early recoveries by accepted coordinates.', '',
              '## Endpoint results', '',
              '| Model | Point | Correct / accepted | Accepted / submitted | Safe or better / accepted |',
              '|---|---|---|---|---|']
    for m, upper in S_STAR.items():
        for target in (10000, upper):
            c = next(c for c in r['cells'] if (c['model_id'], c['scale_target'], c['representation']) == (m, target, 'R0'))
            lines.append(f"| {PRETTY[m]} | {'Anchor' if target == 10000 else f'S* = {target:,}'} | {rate(c['correct'],c['accepted'])} | {rate(c['accepted'],c['submitted'])} | {rate(c['safe_or_better'],c['accepted'])} |")
    lines += ['', 'S* is the largest tested prompt that fitted that model. The nominal 10k anchor contains about '
              '19,435 canonical prompt tokens (pieces of text counted by the common tokenizer).', '',
              '| Model | Anchor minus S* accuracy | Corrected interval | H1-R |', '|---|---|---|---|']
    for m, x in h1['per_model'].items():
        b = x['bootstrap']
        lines.append(f"| {PRETTY[m]} | {b['point']:.4f} | [{b['ci_low']:.4f}, {b['ci_high']:.4f}] | {x['status']} |" if b else f"| {PRETTY[m]} | not evaluable | not evaluable | {x['status']} |")
    lines += ['', 'Intervals use 10,000 bootstrap draws with seed 42. H1-R adjusts for three model comparisons '
              'using Bonferroni: each interval is 98.3333%. The two endpoint samples are resampled separately. '
              'H4 uses the unchanged P9 bootstrap routine; H1-R uses the existing P10 two-sample routine.', '',
              '## Figure and limits', '', LIMITATIONS, '', '![P11 feasibility and recovery accuracy](p11-rescore.svg)', '',
              'The upper panels inherit P10 prompt sizes, backend counts and feasibility classifications. '
              'The lower panels show conditional recovery accuracy with accepted/submitted counts. '
              'The pooled H4 interval and per-model H1-R difference intervals are in the tables above.', '',
              '## Every changed outcome', '',
              '| Representation | Model | Scale | Old outcome | New outcome | Count |', '|---|---|---|---|---|---|']
    for c in r['core_audit']['outcome_changes_by_cell']:
        if c['before'] != c['after']:
            lines.append(f"| {c['representation']} | {PRETTY[c['model_id']]} | {c['scale_target']:,} | {c['before']} | {c['after']} | {c['count']} |")
    lines += ['', 'All per-cell metrics, historical occurrences and verdict-class changes are recorded in '
              '`p11-rescore.json` and `results/rescoring-runs.jsonl`. P10 files remain unchanged. '
              'The grammar is a post-hoc instrument repair relative to P10 collection; only the P11 '
              're-scoring and analysis were pre-registered.', '', '## Reproduce', '',
              'Run `bin/lab-p11-stats --out-dir logs/review/R005/scratch/rebuild`. Compare the JSON, Markdown, '
              'SVG and PNG bytes with these outputs. The tool refuses changed contract digests or a '
              'missing confirmatory-batch record. Run `bin/lab-verify-p11` for the full mechanical checks.', '']
    return '\n'.join(lines)


def figure(r: dict, output: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullFormatter
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'svg.hashsalt': 'p11-fixed'})
    fig, axes = plt.subplots(2, 3, figsize=(12, 7.8), layout='constrained')
    colours = {'R0': '#c75a24', 'R2': '#176ba0'}
    for col, model in enumerate(S_STAR):
        ax = axes[0, col]
        for rep in ('R0', 'R2'):
            cc = [c for c in r['cells'] if c['model_id'] == model and c['representation'] == rep]
            ax.plot([c['scale_target'] for c in cc], [c['canonical_tokens'][0] for c in cc], 'o-',
                    color=colours[rep], markersize=4, label=f'{rep} common count')
            ax.plot([c['scale_target'] for c in cc], [c['backend_prompt_tokens'][0] for c in cc], ':',
                    color=colours[rep], linewidth=1, label=f'{rep} backend count')
            over = [c for c in cc if c['infeasible_p10_units']]
            if over:
                ax.plot([c['scale_target'] for c in over], [c['backend_prompt_tokens'][0] for c in over],
                        'x', color='#292929', markersize=7, label='not submitted')
        ax.axhline(CONTEXT_WINDOWS[model] - MAX_TOKENS, linestyle='--', color='#666666', linewidth=1,
                   label='usable model window')
        ax.set_xscale('log'); ax.set_yscale('log')
        ax.set_ylim(100, 2000000)
        ax.xaxis.set_major_locator(FixedLocator([10000, 100000, 1000000]))
        ax.set_xticklabels(['10k', '100k', '1M']); ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_xlabel('Nominal scale target'); ax.set_title(PRETTY[model], fontweight='bold')
        ax.grid(alpha=.18)
        if col == 0:
            ax.set_ylabel('Prompt size in tokens\n(logarithmic scale)')
        bx = axes[1, col]
        cc = [next(c for c in r['cells'] if (c['model_id'], c['scale_target'], c['representation']) ==
                   (model, target, 'R0')) for target in (10000, S_STAR[model])]
        for x, c in enumerate(cc):
            if c['accuracy'] is not None:
                bx.scatter(x, c['accuracy'], s=60, color=colours['R0'])
                bx.annotate(f"correct {c['correct']}/{c['accepted']}\naccepted {c['accepted']}/{c['submitted']}",
                            (x, c['accuracy']), xytext=(0, -37 if c['accuracy'] > .8 else 13),
                            textcoords='offset points', ha='center', fontsize=9)
        if all(c['accuracy'] is not None for c in cc):
            bx.plot([0, 1], [c['accuracy'] for c in cc], color=colours['R0'], linewidth=1)
        bx.set_xticks([0, 1], ['Anchor\n~19.4k tokens', f'S*\n{S_STAR[model]:,} target'])
        bx.set_xlim(-.5, 1.5); bx.set_ylim(-.12, 1.16); bx.set_yticks([0, .5, 1], ['0%', '50%', '100%'])
        bx.grid(axis='y', alpha=.18)
        bx.set_title('R0 recovery at the two endpoints', fontsize=9)
        if col == 0:
            bx.set_ylabel('Correct / accepted answers')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    axes[0, 0].legend(handles, labels, fontsize=7, loc='center', bbox_to_anchor=(.5, .36), framealpha=.95)
    fig.suptitle('P11: inherited feasibility and re-scored recovery\nOne incident, fixed prompts and three models', fontsize=13)
    fig.savefig(output.with_suffix('.svg'), metadata={'Date': None})
    fig.savefig(output.with_suffix('.png'), dpi=150, metadata={'Software': None})
    plt.close(fig)


def lint(text: str, r: dict) -> dict:
    text = ' '.join(text.split())
    violations = []
    if r['interpretation'] not in text:
        violations.append('matching pre-declared interpretation missing verbatim')
    for pattern in (r'accuracy cliff', r'R2 (?:has superior|is more precise|precision superiority)',
                    r'does not lose accuracy anywhere', r'(?:works|accurate) at (?:any|all) scale'):
        if re.search(pattern, text, re.I):
            violations.append('unsupported phrase: ' + pattern)
    if r['H1-R']['status'] == 'NULL' and 'No degradation' not in text:
        violations.append('null-H1-R statement missing')
    if 'frozen before re-scoring' not in text or 'instrument' not in text:
        violations.append('instrument-repair framing missing')
    return {'ok': not violations, 'violations': violations}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='lab-p11-stats')
    p.add_argument('--out-dir', type=Path, default=root() / 'analysis-out/analysis')
    p.add_argument('--contracts-dir', type=Path, help='read-only contract source, useful for scratch drift tests')
    a = p.parse_args(argv)
    try:
        r = analyse(a.contracts_dir)
        md = render(r)
        checked = lint(md, r)
        if not checked['ok']:
            raise RuntimeError('report lint failed: ' + json.dumps(checked))
        a.out_dir.mkdir(parents=True, exist_ok=True)
        write_json(a.out_dir / 'p11-rescore.json', r)
        (a.out_dir / 'p11-rescore.md').write_text(md)
        figure(r, a.out_dir / 'p11-rescore')
        print(json.dumps({'ok': True, 'H4': r['H4']['status'], 'H1-R': r['H1-R']['status'], 'H3-R': r['H3-R']['status'], 'branch': r['branch']}))
        return 0
    except Exception as exc:
        import sys
        print(f'lab-p11-stats: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
