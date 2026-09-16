"""Validate the preserved unpublished update without inference, promotion or resume."""
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PREVIOUS = BASE / 'recovery_20260905'
RUN = BASE / 'moving256_stage1'
PENDING = RUN / '.latest.pt.c836605996e94811862c30e5da30ad98.pending'
sys.path.insert(0, str(BASE))
import run_control as ctl
import control_evidence as ev


def require_terminal():
    for root in (BASE, PREVIOUS):
        ev.require(not ctl.owner_live(ev.read_json(root / 'ownership.json')), 'controller still live')
    for run in (BASE / 'static_stage1', PREVIOUS / 'static_stage1_remainder', RUN):
        ev.require(not ctl.owner_live(ev.read_json(run / 'process.json')), 'trainer still live')
        receipt = ev.read_json(run / 'termination.json')
        ev.require(not receipt['observer_errors'] and not receipt['remaining_observed_child_pids'], 'incomplete termination')
        for pid, created in receipt['observed_children'].items():
            ev.require(not ctl.owner_live({'pid': int(pid), 'create_time': created}), 'surviving descendant')


def main():
    import torch
    torch.set_num_threads(1)
    require_terminal()
    out = HERE / 'pending_checkpoint_audit.json'
    ev.require(not out.exists(), 'preserve prior audit')
    started = time.perf_counter()
    contract = ev.read_json(PREVIOUS / 'input_contract.json')
    ctl.check_hashes(contract['input_sha256'])
    ev.require(set(RUN.glob('*.pending')) == {PENDING}, 'ambiguous pending candidates')
    files = [p for p in RUN.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [p for p in PREVIOUS.iterdir() if p.is_file()]
    frozen = {str(p): ev.sha(p) for p in files}
    published = torch.load(RUN / 'latest.pt', map_location='cpu', weights_only=False)
    candidate = torch.load(PENDING, map_location='cpu', weights_only=False)
    parent = torch.load(ctl.PARENT, map_location='cpu', weights_only=False)
    initial = torch.load(RUN / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    helper = ctl.qualified_command_helper()
    metrics = ctl.complete_jsonl(RUN / 'h1_training_metrics.jsonl')
    assignments = ctl.complete_jsonl(RUN / 'opponent_assignments.jsonl')
    ev.require([r['iteration'] for r in metrics] == list(range(1, 1216)), 'metric chain gap/duplicate')
    ev.require([r['applies_to_iteration'] for r in assignments] == list(range(1, 1216)), 'assignment chain gap/duplicate')
    for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
        ev.require((RUN / name).read_bytes().endswith(b'\n'), 'incomplete raw tail')
    for checkpoint, row, iteration, physical in ((published, metrics[-2], 1214, 5771740),
                                                (candidate, metrics[-1], 1215, 5776996)):
        ev.require(checkpoint['iteration'] == iteration and checkpoint['total_hands'] == row['hands'] and
                   checkpoint['environment_hand_accounting'] == row['environment_hand_accounting'] and
                   checkpoint['environment_hand_accounting']['completed_hands'] == physical, 'checkpoint/metric mismatch')
        ev.require(all(torch.isfinite(v).all().item() for v in checkpoint['model'].values()), 'nonfinite model')
        ev.require(checkpoint['ppo_replay_cumulative_rows'] == row['ppo_replay_cumulative_rows'] and
                   len(checkpoint['ppo_replay_entries']) == 2 and checkpoint['main_process_rng_state'], 'resume state absent')
    ev.require(candidate['total_hands'] == 5006429 and
               min(helper.steps(candidate)) > max(helper.steps(published)), 'unpublished optimizer update missing')
    ev.require(not helper.equal(candidate['model'], published['model']), 'unpublished weights did not change')
    ev.require([g['lr'] for g in candidate['optimizer']['param_groups']] ==
               [g['lr'] for g in published['optimizer']['param_groups']], 'learning rate changed')
    manifest = ev.read_json(RUN / 'run_manifest.json')
    ev.require(manifest['iteration'] == candidate['iteration'], 'manifest does not include candidate update')
    attempt = candidate['fixed_deal_attempt']
    receipt = helper.helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
    ev.require(receipt == attempt['receipt'] and
               receipt['namespace'] == published['fixed_deal_attempt']['receipt']['namespace'] and
               receipt['parent_checkpoint_sha256'] == ctl.PARENT_SHA, 'attempt receipt changed')
    trainer = ev.module_at('seed3_second_interruption_assignment_replay', ctl.PRODUCTION)
    assignment_replay = trainer.restore_group_assignment_rng_from_evidence(assignments, metrics, rng=random.Random(0),
        seed=ctl.TRAINING_SEED, worker_count=12, pool_size=len(candidate['pool_snapshots']), group_count=8,
        self_play_fraction=.25, checkpoint_iteration=candidate['iteration'], checkpoint_total_hands=candidate['total_hands'],
        pool_snapshot_ids=[r['id'] for r in candidate['pool_active_metadata']],
        replay_origin=candidate.get('assignment_replay_origin'))
    ev.require(assignment_replay['pending_assignments'] is None, 'unexpected assignment beyond candidate update')
    pool = ev.module_at('seed3_pending_pool_windows', ctl.POOL_HELPER)
    windows, references = [pool.load_window(ctl.PARENT, ctl.PARENT_SHA)], []
    paths = [*sorted((RUN / 'checkpoints').glob('*.pt')), *sorted(RUN.glob('phase_iter*.pt')),
             RUN / 'latest.pt', PENDING]
    for path in paths:
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        ev.require(parent['iteration'] < checkpoint['iteration'] <= candidate['iteration'], 'bad archive boundary')
        windows.append(pool.load_window(path, frozen[str(path)]))
        references.append({k: checkpoint[k] for k in ('iteration', 'model', 'environment_hand_accounting')}
                          | {'moving_source_policy_reference': checkpoint.get('moving_source_policy_reference')})
    windows.sort(key=lambda w: w['iteration'])
    references.sort(key=lambda w: w['iteration'])
    pool_audit = pool.verify_windows(windows, metrics, assignments)
    reference_audit = ev.verify_reference_windows('moving256', parent, initial, references, metrics, helper.equal)
    ev.require(helper.finite_update_evidence([r for r in metrics if r['iteration'] > parent['iteration']],
               (RUN / 'latest_train.log').read_text(encoding='utf-8')), 'nonfinite or missing update evidence')
    static_run = PREVIOUS / 'static_stage1_remainder'
    static = ev.read_json(static_run / 'verification.json')
    ev.require(static['passed'] and ev.sha(static_run / 'latest.pt') == static['checkpoint_sha256'], 'completed static endpoint changed')
    old_static = ev.read_json(PREVIOUS / 'interruption_audit.json')
    physical = candidate['environment_hand_accounting']['completed_hands']
    retained = physical - ctl.INITIAL_PHYSICAL
    transition = candidate['total_hands'] - parent['total_hands']
    no_decision = candidate['environment_hand_accounting']['no_trainable_decision_hands'] - parent['environment_hand_accounting']['no_trainable_decision_hands']
    total_retained = retained + static['new_physical_hands'] + old_static['new_retained_physical_hands']
    inputs = {**contract['input_sha256'], **frozen, str(Path(__file__).resolve()): ev.sha(__file__),
              str(static_run / 'verification.json'): ev.sha(static_run / 'verification.json'),
              str(static_run / 'latest.pt'): static['checkpoint_sha256'], attempt['path']: attempt['sha256']}
    ctl.check_hashes(inputs)
    result = {'schema': 'cardpilot.seed3.second_interruption.pending_audit.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
        'wall_seconds': time.perf_counter() - started, 'all_prior_owners_and_observed_children_terminal': True,
        'candidate_path': str(PENDING), 'candidate_sha256': frozen[str(PENDING)],
        'published_sha256': frozen[str(RUN / 'latest.pt')], 'candidate_iteration': candidate['iteration'],
        'candidate_physical_hands': physical, 'candidate_transition_hands': candidate['total_hands'],
        'published_iteration': published['iteration'], 'unpublished_completed_update_physical_hands': physical -
            published['environment_hand_accounting']['completed_hands'],
        'unpublished_completed_update_transition_hands': candidate['total_hands'] - published['total_hands'],
        'recoverable_new_physical_hands': retained, 'recoverable_new_transition_hands': transition,
        'recoverable_new_replay_rows': candidate['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'],
        'recoverable_new_no_decision_hands': no_decision, 'recoverable_worker_tail_hands': retained - transition - no_decision,
        'known_completed_but_not_serialized_hands_in_this_attempt': 0,
        'unknown_additional_worker_tail_hands': None,
        'namespace': receipt['namespace'], 'assignment_replay': assignment_replay,
        'pool_window_audit': pool_audit, 'moving_reference_audit': reference_audit,
        'candidate_main_rng_present': True, 'candidate_replay_entries': len(candidate['ppo_replay_entries']),
        'effective_optimizer_lr': [g['lr'] for g in candidate['optimizer']['param_groups']],
        'remaining_stage1_physical_hands': ctl.TARGETS[1] - physical,
        'same_experiment_retained_training_hands_if_candidate_adopted': total_retained,
        'same_experiment_observed_training_hands': total_retained + old_static['observed_completed_but_uncheckpointed_physical_hands'],
        'first_interruption_unretained_hands_still_separate': old_static['observed_completed_but_uncheckpointed_physical_hands'],
        'candidate_promoted_or_training_restarted': False,
        'failure_time_access_denial_cause_beyond_os_replace': None,
        'frozen_second_interruption_inputs': frozen, 'input_sha256': inputs,
        'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0,
        'next_step': 'Qualify bounded I/O recovery then derive an immutable candidate parent and resume only remaining hands with a new namespace.'}
    ctl.write_new(out, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('input_sha256', 'frozen_second_interruption_inputs')}, indent=2))


if __name__ == '__main__':
    main()
