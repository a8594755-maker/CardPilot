"""Frozen preregistered matrix after the original training wrapper terminates.

Waiting never restarts training. Completed matrix cells are verified and reused;
partial cells are preserved and require inspection, never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance

ID = 'physical-budget-1m-learning-curve-20260830'
BASE = Path('research/experiments') / ID
RUN = BASE / 'production'
SEED = 20260893
MODES = [('greedy', 'greedy_argmax_both_sides', 2048), ('sampled', 'sampled_both_sides', 4096)]
ACTION_RNG_SCHEMA = 'sha256_seed_pair_physical_seat_decision_v1'
ANCHORS = [
    ('standard10', 'models/baseline/standard10/latest.pt',
     '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'),
    ('slumbot_free', 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt',
     '457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7'),
    ('corrected_cfr96', 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt',
     '902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6'),
]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID,
                    *map(str, args)], cwd=ROOT, check=True)


def choose_archives(rows, final):
    ordered = sorted(rows, key=lambda r: r['iteration'])
    if not ordered or len({r['iteration'] for r in ordered}) != len(ordered):
        raise ValueError('Missing or duplicate archive iterations')
    if any(not r['prefix_complete'] for r in [*ordered, final]):
        raise ValueError('Physical prefix is incomplete')
    if any(b['physical_hands'] <= a['physical_hands'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Non-monotone physical archive counters')
    if final['physical_hands'] < 1048576 or final['physical_hands'] < ordered[-1]['physical_hands']:
        raise ValueError('Final physical target is incomplete')
    selected = {}
    for label, target in [('early', 262144), ('mid', 524288)]:
        eligible = [r for r in ordered if r['physical_hands'] >= target]
        if not eligible:
            raise ValueError(f'No archive meets {label} physical budget')
        selected[label] = eligible[0]
    selected['final'] = final
    return selected


def validate_cell(document, execution, candidate_sha, mode, pairs):
    if execution.get('status') != 'COMPLETED' or document.get('execution', {}).get('status') != 'COMPLETED':
        raise ValueError('Incomplete evaluator execution')
    for key, expected in [('seed', SEED), ('pairs', pairs), ('starting_stack', 200.0), ('policy_mode', mode)]:
        if document.get(key) != expected:
            raise ValueError(f'Cell configuration mismatch: {key}')
    if document['candidate']['sha256'] != candidate_sha:
        raise ValueError('Candidate SHA mismatch')
    expected_anchors = {label: digest for label, _, digest in ANCHORS}
    if len(document['anchors']) != len(expected_anchors):
        raise ValueError('Wrong anchor count')
    if {r['anchor']: r['anchor_sha256'] for r in document['anchors']} != expected_anchors:
        raise ValueError('Anchor identity mismatch')
    expected_schema = ACTION_RNG_SCHEMA if mode == 'sampled_both_sides' else None
    if document.get('action_rng_schema') != expected_schema:
        raise ValueError('Action RNG schema mismatch')
    for index, row in enumerate(document['anchors']):
        if row['anchor'] != ANCHORS[index][0]:
            raise ValueError('Anchor order mismatch')
        expected_rng = {'schema': ACTION_RNG_SCHEMA, 'seed': SEED + index * 1000003} if expected_schema else None
        if row.get('action_rng') != expected_rng:
            raise ValueError('Action RNG stream mismatch')
        if row.get('pairs') != pairs or row.get('hands') != 2 * pairs:
            raise ValueError('Per-anchor hand count mismatch')
        outcomes = row['paired_outcomes']
        if any(len(outcomes.get(key, [])) != pairs for key in
               ['overall_bb_per_hand', 'bb_bb_per_hand', 'sb_bb_per_hand']):
            raise ValueError('Incomplete raw pair evidence')
        for overall, bb, sb in zip(outcomes['overall_bb_per_hand'], outcomes['bb_bb_per_hand'], outcomes['sb_bb_per_hand']):
            if not all(math.isfinite(x) and abs(x) <= 200 for x in [overall, bb, sb]):
                raise ValueError('Non-finite or out-of-stack raw evidence')
            if abs(overall - (bb + sb) / 2) > 1e-9:
                raise ValueError('Raw paired-seat mismatch')
        bb100 = sum(outcomes['overall_bb_per_hand']) * 100 / pairs
        if abs(bb100 - row['candidate_bb100']) > 1e-8:
            raise ValueError('Raw outcome / reported score mismatch')
    return len(expected_anchors) * 2 * pairs


def code_snapshot(reuse=False):
    snapshot = ROOT / BASE / 'evaluation_code'
    if reuse:
        copies = json.loads((snapshot / 'copy_manifest.json').read_text())
        for row in copies:
            if sha(ROOT / row['copy']) != row['sha256']:
                raise ValueError('Prepared evaluation source changed')
        own_copy = snapshot / 'source_files' / BASE / 'run_evaluation.py'
        if sha(Path(__file__)) != sha(own_copy):
            raise ValueError('Resume launcher differs from frozen execution source')
        return snapshot, [str(BASE / 'evaluation_code/code.patch'), str(BASE / 'evaluation_code/source_manifest.json')]
    snapshot.mkdir(exist_ok=False)
    code = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'scripts/alpha_holdem').glob('*.py'))]
    code += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    code += [str(BASE / 'run_evaluation.py'), str(BASE / 'test_evaluation_runner.py'), 'research/experiment_log.py']
    _, artifacts = capture_code_provenance(ROOT, snapshot, code)
    copies = []
    for relative in code:
        src, dst = ROOT / relative, snapshot / 'source_files' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        assert sha(src) == sha(dst)
        copies.append({'original': relative, 'copy': dst.relative_to(ROOT).as_posix(), 'sha256': sha(dst)})
    (snapshot / 'copy_manifest.json').write_text(json.dumps(copies, indent=2) + '\n')
    return snapshot, artifacts


def wait_for_wrapper(pid):
    if not pid:
        return
    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return  # Terminal evidence is still required below; absence never triggers restart.
    command = ' '.join(process.cmdline())
    if ID not in command or 'run_training.py' not in command:
        raise ValueError('Wait PID is not the expected training wrapper')
    created = process.create_time()
    (ROOT / BASE / 'evaluation_wait_state.json').write_text(json.dumps({
        'pid': pid, 'process_created': created, 'command': command,
        'status': 'WAITING_FOR_ORIGINAL_WRAPPER', 'no_record_writes_until_wrapper_exit': True,
    }, indent=2) + '\n')
    while process.is_running():
        try:
            if process.create_time() != created:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(10)


def freeze_selection(reuse=False):
    if reuse and (ROOT / BASE / 'checkpoint_selection.json').exists():
        selection = json.loads((ROOT / BASE / 'checkpoint_selection.json').read_text())['selected']
        for row in selection.values():
            if sha(ROOT / row['evaluation_path']) != row['sha256']:
                raise ValueError('Frozen evaluation checkpoint changed')
        return selection
    import torch
    def metadata(path):
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        accounting = checkpoint['environment_hand_accounting']
        if checkpoint['run_id'] != 'physical_budget_1m_20260830':
            raise ValueError('Checkpoint run identity mismatch')
        return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
                'iteration': checkpoint['iteration'], 'legacy_marker_hands': checkpoint['total_hands'],
                'physical_hands': accounting['completed_hands'], 'prefix_complete': accounting['prefix_complete']}
    rows = [metadata(p) for p in sorted((ROOT / RUN / 'checkpoints').glob('checkpoint_*.pt'))]
    selected = choose_archives(rows, metadata(ROOT / RUN / 'latest.pt'))
    frozen = ROOT / BASE / 'frozen'
    frozen.mkdir(exist_ok=False)
    for label, row in selected.items():
        dest = frozen / f'{label}.pt'
        shutil.copy2(ROOT / row['path'], dest)
        assert sha(dest) == row['sha256']
        row['evaluation_path'] = dest.relative_to(ROOT).as_posix()
    selected['source'] = {'evaluation_path': ANCHORS[0][1], 'sha256': ANCHORS[0][2], 'physical_hands': 0}
    selection_path = ROOT / BASE / 'checkpoint_selection.json'
    selection_path.write_text(json.dumps({'selection_rule': 'first_archive_at_or_above_budget',
                                         'archives': rows, 'selected': selected}, indent=2) + '\n')
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-for-pid', type=int, default=0)
    parser.add_argument('--resume-evaluation', action='store_true')
    args = parser.parse_args()
    snapshot, artifacts = code_snapshot(reuse=args.resume_evaluation)
    wait_for_wrapper(args.wait_for_pid)
    # Do not race an orphan trainer if its wrapper failed.
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = ' '.join(process.info['cmdline'] or [])
        if process.pid != psutil.Process().pid and 'train_v5.py' in command and 'physical_budget_1m_20260830' in command:
            raise RuntimeError('Original trainer is still live; evaluation will not start')
    record = json.loads((ROOT / BASE / 'experiment.json').read_text())
    audit = json.loads((ROOT / BASE / 'production_audit.json').read_text())
    if record['metrics'].get('training_complete') != 1 or audit['status'] != 'PASS':
        raise RuntimeError('Training completion and session audit are required')
    log('--command', subprocess.list2cmdline(['python', str(BASE / 'run_evaluation.py'), *sys.argv[1:]]),
        '--artifact', str(BASE / 'evaluation_code/copy_manifest.json'),
        *[item for artifact in artifacts for item in ['--artifact', artifact]])
    for _, path, digest in ANCHORS:
        if sha(ROOT / path) != digest:
            raise ValueError('Frozen anchor changed')
    selected = freeze_selection(reuse=args.resume_evaluation)
    log('--artifact', str(BASE / 'checkpoint_selection.json'), '--metric', 'evaluation_started=1',
        '--note', 'Original wrapper has terminated, completed physical endpoint and session audit PASS. Frozen budget-only selection; no concurrent record writer remains. Evaluator executes immutable snapshot including deep_cfr dependencies.')
    evaluation_script = snapshot / 'source_files/scripts/alpha_holdem/v5_mirror_eval.py'
    delta_script = snapshot / 'source_files/scripts/alpha_holdem/paired_mirror_treatment_delta.py'
    evidence_hands = 0
    matrix = {}
    for mode_label, mode, pairs in MODES:
        for label in ['source', 'early', 'mid', 'final']:
            candidate = selected[label]
            prefix = BASE / 'matrix' / f'{mode_label}_{label}'
            paths = {'json': ROOT / f'{prefix}.json', 'md': ROOT / f'{prefix}.md',
                     'execution': ROOT / f'{prefix}_execution.json', 'stdout': ROOT / f'{prefix}_stdout.log'}
            command = [str(evaluation_script), '--candidate', str(ROOT / candidate['evaluation_path']),
                       '--candidate-label', f'physical_1m_{label}', '--policy-mode', mode,
                       '--pairs', str(pairs), '--starting-stack', '200', '--seed', str(SEED),
                       '--include-pair-outcomes', '--device', 'cuda', '--priority', 'below-normal',
                       '--out-json', str(paths['json']), '--out-md', str(paths['md']),
                       '--execution-json', str(paths['execution'])]
            for anchor, path, _ in ANCHORS:
                command += ['--anchor', f'{anchor}={ROOT / path}']
            log('--command', subprocess.list2cmdline(['python', *command]))
            if not paths['json'].exists():
                if any(path.exists() for path in paths.values()):
                    raise RuntimeError(f'Partial cell must be inspected, not overwritten: {prefix}')
                paths['stdout'].parent.mkdir(parents=True, exist_ok=True)
                with paths['stdout'].open('x', encoding='utf-8') as output:
                    subprocess.run([sys.executable, *command], cwd=ROOT, stdout=output,
                                   stderr=subprocess.STDOUT, check=True)
            document = json.loads(paths['json'].read_text())
            execution = json.loads(paths['execution'].read_text())
            evidence_hands += validate_cell(document, execution, candidate['sha256'], mode, pairs)
            if sha(ROOT / candidate['evaluation_path']) != candidate['sha256']:
                raise ValueError('Candidate bytes changed during evaluation')
            matrix[f'{mode_label}_{label}'] = {'path': str(paths['json'].relative_to(ROOT)),
                'sha256': sha(paths['json']), 'ood_valid': document['gate']['all_anchors_pass_ood_gate']}
            log('--count', f'evaluation_hands={evidence_hands}',
                *[item for path in paths.values() for item in ['--artifact', str(path.relative_to(ROOT))]])
            if label != 'source':
                delta_path = ROOT / f'{prefix}_delta.json'
                delta = [str(delta_script), '--control', str(ROOT / BASE / 'matrix' / f'{mode_label}_source.json'),
                         '--treatment', str(paths['json']), '--out', str(delta_path)]
                log('--command', subprocess.list2cmdline(['python', *delta]))
                if not delta_path.exists():
                    subprocess.run([sys.executable, *delta], cwd=ROOT, check=True)
                result = json.loads(delta_path.read_text())
                control_path = ROOT / BASE / 'matrix' / f'{mode_label}_source.json'
                if result['control']['sha256'] != sha(control_path) or result['treatment']['sha256'] != sha(paths['json']):
                    raise ValueError('Existing delta evidence hash mismatch')
                eligible = (document['gate']['all_anchors_pass_ood_gate'] and
                            matrix[f'{mode_label}_source']['ood_valid'] and
                            result['summary']['all_point_estimates_positive'] and
                            any(r['paired_ci95_lower_bb100'] > 0 for r in result['anchors']))
                matrix[f'{mode_label}_{label}'].update(
                    delta=result['summary'], admits_independent_confirmation=eligible,
                    primary_endpoint=(label == 'final'))
                log('--artifact', str(delta_path.relative_to(ROOT)))
    assert evidence_hands == 147456
    summary_path = ROOT / BASE / 'matrix_summary.json'
    summary = {'evaluation_hands': evidence_hands, 'cells': matrix,
        'claim_scope': 'exploratory_internal_only_not_slumbot',
        'multiple_testing': 'Admission gate only; any selected gain needs independent confirmation.'}
    if summary_path.exists():
        if json.loads(summary_path.read_text()) != summary:
            raise ValueError('Existing matrix summary differs')
    else:
        summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    log('--artifact', str(summary_path.relative_to(ROOT)), '--metric', 'discovery_matrix_complete=1',
        '--note', 'Prespecified greedy2048/sample4096 pairs x3 anchors x4 checkpoints completed. Analyze primary final endpoint and full learning curve before record finish; admission alone is not a general strength claim.')


if __name__ == '__main__':
    main()
