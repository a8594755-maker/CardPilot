"""Fresh-data temporal-mixture distillation; never accesses an external opponent."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
TRAIN = ROOT/'research/experiments/v6-average-response-oracle-pilot-20260831'
EXTERNAL = ROOT/'research/experiments/v6-historical-average-fresh20k-slumbot-20260831'
CORPUS = ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01/states.jsonl'
SOURCE_SHA = 'cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b'
FINAL_SHA = '58ef62e875ce8ad1ecf518a1a65c8f54ba711b3bc1ea1a3ab3a00ed1e1a3540d'
REVIEW_SHA = 'ff2f49d0240d95f17f93441d39d57b2a02c23f770020a71b6b83260d7b9db2d0'
EPOCHS, TEACHERS = 4, 2
TRAIN_HANDS, VALID_HANDS = 262144, 8192
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    atomic_json(BASE/name, value)


def sha(path):
    return sha256_file(Path(path))


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def preserved_failure_accounting(phase):
    counts = {}
    for split in ('training', 'validation'):
        path = BASE/f'{split}_hands.jsonl'
        counts[split] = path.read_bytes().count(b'\n') if path.exists() else 0
    # The unchanged collector writes full hand rows at1024-hand barriers. A
    # failed in-flight barrier can contain additional terminal hands only in RAM.
    active = {'TRAINING_DATA':('training', TRAIN_HANDS), 'SUPERVISED_VALIDATION':('validation', VALID_HANDS)}.get(phase)
    upper = min(1024, max(0, active[1]-counts[active[0]])) if active else 0
    return dict(status='FAILED_PRESERVED', phase=phase, preserved_complete_raw_lines=counts,
        additional_unserialized_terminal_hands_unknown=bool(upper), additional_unserialized_terminal_hands_upper_bound=upper,
        exact_actual_hand_totals_claimed=False, automatic_resume_qualified=False,
        accounting_interpretation='Preserved complete raw hand claims only; an in-flight barrier is not silently counted as zero or replayed.')


def snapshot_code():
    directory = BASE/'execution_code'
    directory.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{name}.py' for name in ('__init__', 'game_state', 'hand_eval')]
    paths += ['research/experiment_log.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md'}]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for path in paths:
        target = directory/'source_files'/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/path, target)
        copies.append(dict(original=path, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    write('execution_code/copy_manifest.json', copies)
    log(*[v for name in ('source_manifest.json', 'code.patch', 'copy_manifest.json') for v in ('--artifact', directory/name)])
    return copies


def verify(copies, inputs):
    require_admission()
    for row in copies:
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ('original', 'copy'))
    for row in inputs['teachers']:
        assert sha(row['source']) == sha(row['path']) == row['sha256']
    for row in inputs['dependencies']:
        assert sha(row['path']) == row['sha256']


def validate_response_review(review, digest):
    assert review['status'] == 'PASS' and review['decision'] == 'ADMIT_SEPARATE_AVERAGE_UPDATE'
    assert review['training_health']['checkpoint_sha256'] == digest
    assert review['new_training_hands'] >= 1048576 and review['evaluation_hands'] == 196608
    assert review['primary']['ci95'][0] > 0
    assert review['slumbot_hands'] == review['qualification_hands'] == 0 and not review['goal_achieved']


def require_admission():
    if not (isinstance(FINAL_SHA, str) and len(FINAL_SHA) == 64 and isinstance(REVIEW_SHA, str) and len(REVIEW_SHA) == 64):
        raise ValueError('Response admission hashes not frozen; no collection or output creation')
    assert read(TRAIN/'experiment.json')['status'] == 'COMPLETED'
    assert sha(TRAIN/'reviewed_analysis.json') == REVIEW_SHA
    validate_response_review(read(TRAIN/'reviewed_analysis.json'), FINAL_SHA)
    assert sha(TRAIN/'frozen/final.pt') == FINAL_SHA
    assert sha(TRAIN/'frozen/average.pt') == SOURCE_SHA
    assert sha(CORPUS) == 'da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d'
    for row in read(TRAIN/'execution_code/copy_manifest.json'):
        assert sha(ROOT/row['copy']) == row['sha256']
        if row['original'].startswith('scripts/'):
            assert sha(ROOT/row['original']) == row['sha256']


def freeze_teachers():
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    require_admission()
    (BASE/'teachers').mkdir()
    teachers = []
    for index, (name, expected) in enumerate([('average', SOURCE_SHA), ('final', FINAL_SHA)]):
        path = TRAIN/'frozen'/f'{name}.pt'
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        validate_metadata(checkpoint)
        assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
        assert sha(path) == expected
        target = BASE/'teachers'/f'teacher{index:02d}.pt'
        shutil.copy2(path, target)
        teachers.append(dict(index=index, role='previous_average' if index == 0 else 'new_response',
            source=str(path), path=str(target), sha256=sha(target), probability=.5))
    dependencies = [dict(path=str(p), sha256=sha(p)) for p in
        (CORPUS, TRAIN/'reviewed_analysis.json', TRAIN/'production/h1_training_metrics.jsonl')]
    result = dict(teachers=teachers, dependencies=dependencies, collection_hands=TRAIN_HANDS,
        supervised_validation_hands=VALID_HANDS, slumbot_hands=0, source_training_hands_recounted=0,
        normal_form_mixture_weights=[.5, .5], phase=1, response_review_sha256=REVIEW_SHA)
    write('input_manifest.json', result)
    log('--artifact', BASE/'input_manifest.json', *[v for row in teachers for v in ('--artifact', row['path'])])
    return result

def qualify(models, inputs):
    import numpy as np
    from alpha_holdem.policy_contract_v6 import observation, from_external
    from alpha_holdem.execution_v6 import load_policy, decide
    from temporal_average import batch_probs
    rows = []
    with CORPUS.open() as handle:
        for _, line in zip(range(64), handle):
            rows.append(json.loads(line))
    states = [from_external(r['action'], r['hole_cards'], r['board'], r['seat']) for r in rows]
    observations = [observation(s)[0] for s in states]
    evidence = []
    for index, gpu in enumerate(models):
        cpu, _, _ = load_policy(inputs['teachers'][index]['path'], 'cpu')
        direct = np.asarray([decide(cpu, state, uniform=.371)[1]['behavior_probs'] for state in states])
        cb, gb = batch_probs(cpu, observations, 'cpu'), batch_probs(gpu, observations, 'cuda')
        cpu_error, gpu_error = float(np.abs(cb-direct).max()), float(np.abs(gb-direct).max())
        assert max(cpu_error, gpu_error) <= 2e-5
        evidence.append(dict(teacher=index, states=64, cpu_max_absolute_error=cpu_error, gpu_max_absolute_error=gpu_error))
    result = dict(status='PASS', teachers=TEACHERS, states_per_teacher=64, policy_state_queries=TEACHERS*64*3,
                  new_hands=0, comparison='CPU scalar versus CPU/GPU batches', evidence=evidence)
    write('batch_qualification.json', result)
    log('--artifact', BASE/'batch_qualification.json')


def validation_dataset(path):
    import numpy as np
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import observation, apply_incr
    from temporal_average import KEYS
    arrays, targets, hands = {k: [] for k in KEYS}, [], []
    with Path(path).open() as handle:
        for line in handle:
            row = json.loads(line)
            state = ChipState.new(row['deck'])
            for event in row['events']:
                obs = observation(state)[0]
                for k in KEYS:
                    arrays[k].append(obs[k])
                targets.append(event['probabilities'])
                hands.append(row['index'])
                state = apply_incr(state, event['increment'])
    return {k: np.stack(v) for k, v in arrays.items()}, np.asarray(targets, dtype=np.float32), np.asarray(hands)


def fit_student(inputs, reservoir):
    import numpy as np
    import torch
    from alpha_holdem.execution_v6 import load_policy
    from alpha_holdem.policy_contract_v6 import METADATA
    from temporal_average import KEYS, soft_ce
    torch.manual_seed(2026101504)
    torch.cuda.manual_seed_all(2026101504)
    student, source, _ = load_policy(inputs['teachers'][0]['path'], 'cuda')
    initial = {k: v.detach().cpu().clone() for k, v in student.state_dict().items()}
    names = []
    for name, parameter in student.named_parameters():
        trainable = not name.startswith('value_head.')
        parameter.requires_grad_(trainable)
        if trainable:
            names.append(name)
    assert names and any('preflop_policy_head' in n for n in names)
    optimizer = torch.optim.Adam([p for p in student.parameters() if p.requires_grad], lr=1e-4)
    generator = np.random.default_rng(2026101504)
    val_arrays, val_targets, val_hands = validation_dataset(BASE/'validation_hands.jsonl')
    assert len(np.unique(val_hands)) == VALID_HANDS

    @torch.no_grad()
    def losses():
        student.eval()
        values = []
        for start in range(0, len(val_targets), 1024):
            ts = [torch.as_tensor(val_arrays[k][start:start+1024], device='cuda') for k in KEYS]
            target = torch.as_tensor(val_targets[start:start+1024], device='cuda')
            values.extend(soft_ce(student(*ts)[0], target, ts[-1]).cpu().tolist())
        values = np.asarray(values)
        assert np.isfinite(values).all()
        return values

    baseline = losses()
    np.save(BASE/'validation_source_ce.npy', baseline)
    (BASE/'checkpoints').mkdir()
    steps = 0
    history = []
    with (BASE/'training_metrics.jsonl').open('x') as handle:
        for epoch in range(1, EPOCHS+1):
            student.train()
            order, total_loss, count = generator.permutation(len(reservoir)), 0., 0
            for start in range(0, len(order), 1024):
                idx = order[start:start+1024]
                ts = [torch.as_tensor(reservoir.arrays[k][idx], device='cuda') for k in KEYS]
                targets = torch.as_tensor(reservoir.targets[idx], dtype=torch.float32, device='cuda')
                optimizer.zero_grad(set_to_none=True)
                loss = soft_ce(student(*ts)[0], targets, ts[-1]).mean()
                assert torch.isfinite(loss)
                loss.backward()
                norm = torch.nn.utils.clip_grad_norm_([p for p in student.parameters() if p.requires_grad], 1.)
                assert torch.isfinite(norm)
                optimizer.step()
                steps += 1
                value = float(loss.detach())
                handle.write(json.dumps(dict(epoch=epoch, step=steps, rows=len(idx), loss=value,
                    gradient_norm=float(norm), new_training_hands=TRAIN_HANDS))+'\n')
                total_loss += value*len(idx)
                count += len(idx)
            handle.flush()
            os.fsync(handle.fileno())
            if epoch in (1, EPOCHS):
                current = losses()
                summary = dict(epoch=epoch, step=steps, training_ce=total_loss/count, validation_ce=float(current.mean()))
                history.append(summary)
                print(json.dumps(summary), flush=True)
                np.save(BASE/f'validation_epoch{epoch:02d}_ce.npy', current)
            assert all(torch.isfinite(v).all() for v in student.state_dict().values())
            checkpoint = dict(**METADATA, model={k: v.detach().cpu().clone() for k, v in student.state_dict().items()},
                optimizer=optimizer.state_dict(), config={**source.get('config', {}), 'training_algorithm':'fictitious_average_phase1_distillation_v1',
                'lr':1e-4, 'seed':2026101504}, critic_contract=source.get('critic_contract', 'critic_v2'),
                norm_layer='gn', separate_preflop_head=True, epoch=epoch, iteration=epoch, total_hands=TRAIN_HANDS,
                optimizer_steps=steps, run_id=BASE.name, training_algorithm='fictitious_average_phase1_distillation_v1',
                source_weights_sha256=SOURCE_SHA, input_manifest_sha256=sha(BASE/'input_manifest.json'),
                dataset_sha256=sha(BASE/'reservoir.pt'), numpy_generator_state=generator.bit_generator.state,
                torch_rng_state=torch.get_rng_state(), cuda_rng_state=torch.cuda.get_rng_state_all(),
                environment_hand_accounting=dict(completed_hands=TRAIN_HANDS, prefix_complete=True,
                unknown_prefix_training_marker_hands=0, origin_run_id=BASE.name,
                semantics='unique physical training-data collection hands; supervised epochs add zero environment hands'),
                resume_contract='Not a train_v5 PPO continuation; requires explicit supervised-only resume')
            temporary = BASE/'latest.tmp.pt'
            torch.save(checkpoint, temporary)
            os.replace(temporary, BASE/'latest.pt')
            if epoch in (1, EPOCHS):
                shutil.copy2(BASE/'latest.pt', BASE/'checkpoints'/f'epoch{epoch:02d}.pt')
            write('fit_progress.json', dict(epoch=epoch, optimizer_steps=steps, fixed_final_epoch=EPOCHS))
    final = losses()
    improvement = baseline-final
    sums = np.bincount(val_hands, weights=improvement, minlength=VALID_HANDS)
    counts = np.bincount(val_hands, minlength=VALID_HANDS)
    assert (counts > 0).all()
    hand_means = sums/counts
    mean, se = float(hand_means.mean()), float(hand_means.std(ddof=1)/math.sqrt(VALID_HANDS))
    changed = [k for k, v in student.state_dict().items() if not torch.equal(v.detach().cpu(), initial[k])]
    assert all(not k.startswith('value_head.') for k in changed) and set(changed) == set(names)
    assert len(optimizer.state) == len(names) and all(float(v['step']) == steps for v in optimizer.state.values())
    for state in optimizer.state.values():
        assert all(torch.isfinite(v).all() for v in state.values() if torch.is_tensor(v))
    np.save(BASE/'validation_hand_ce_improvement.npy', hand_means)
    result = dict(status='PASS', epochs=EPOCHS, optimizer_steps=steps, trainable_changed_parameters=changed,
        frozen_value_parameters=[k for k in initial if k.startswith('value_head.')], source_ce=float(baseline.mean()),
        final_ce=float(final.mean()), hand_mean_ce_improvement=mean, hand_ci95=[mean-1.96*se, mean+1.96*se],
        history=history, model_sha256=sha(BASE/'latest.pt'), new_training_hands=TRAIN_HANDS,
        supervised_validation_hands=VALID_HANDS, validation_decisions=len(val_targets),
        decision='ADMIT_SEPARATE_AVERAGE_ASSESSMENT' if mean-1.96*se > 0 else 'AVERAGE_UPDATE_FIT_GATE_NOT_PASSED')
    write('fit_analysis.json', result)
    return result


def main():
    require_admission()
    import psutil
    import torch
    if sys.argv[1:] or any((BASE/name).exists() for name in ('execution.json', 'execution_code', 'teachers', 'training_hands.jsonl')):
        raise ValueError('No collector restart/resume/overwrite')
    for process in psutil.process_iter(['name', 'cmdline']):
        if process.pid != os.getpid() and (process.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ('train_v5.py', 'run_transfer.py', 'run_distillation.py', 'run_pilot.py', 'v6_mirror_eval.py', 'play_slumbot_v6_journaled.py') for a in process.info['cmdline'] or []):
            raise ValueError('Other live poker process')
    assert torch.cuda.is_available() and psutil.virtual_memory().available > 16*2**30
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
    start = time.time()
    execution = dict(status='PREPARING', pid=os.getpid(), create_time=psutil.Process().create_time(),
                     started_at=datetime.now(timezone.utc).isoformat(), command=[sys.executable, *sys.argv],
                     new_training_hands=0, supervised_validation_hands=0, slumbot_hands=0)
    write('execution.json', execution)
    success = False
    try:
        copies = snapshot_code()
        sys.path.insert(0, str(BASE/'execution_code/source_files/scripts'))
        from alpha_holdem.execution_v6 import load_policy
        from temporal_average import Reservoir, collect, audit_trace
        cmd = ['-m', 'pytest', str(BASE/'test_temporal_average.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
        log('--command', subprocess.list2cmdline(['python', *cmd]))
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        inputs = freeze_teachers()
        verify(copies, inputs)
        models = [load_policy(row['path'], 'cuda')[0] for row in inputs['teachers']]
        qualify(models, inputs)
        reservoir = Reservoir(262144, 2026101503)
        def progress(phase, completed, decisions):
            key = 'new_training_hands' if phase == 'TRAINING_DATA' else 'supervised_validation_hands'
            execution.update(status=phase, **{key: completed}, decisions_in_phase=decisions, wall_time_seconds=time.time()-start)
            write('execution.json', execution)
            log('--count', f'new_training_hands={execution["new_training_hands"]}', '--count', f'evaluation_hands={execution["supervised_validation_hands"]}',
                '--count', f'supervised_validation_hands={execution["supervised_validation_hands"]}')
            print(json.dumps(dict(phase=phase, completed_hands=completed, decisions=decisions)), flush=True)
        execution['status'] = 'TRAINING_DATA'
        write('execution.json', execution)
        training = collect(models, seed=2026101501, hands=TRAIN_HANDS, out=BASE/'training_hands.jsonl', reservoir=reservoir,
                           progress=lambda n, d: progress('TRAINING_DATA', n, d))
        torch.save(reservoir.state_dict(), BASE/'reservoir.pt')
        log('--artifact', BASE/'reservoir.pt', '--artifact', BASE/'training_hands.jsonl')
        execution['status'] = 'SUPERVISED_VALIDATION'
        write('execution.json', execution)
        validation = collect(models, seed=2026101502, hands=VALID_HANDS, out=BASE/'validation_hands.jsonl',
                             progress=lambda n, d: progress('SUPERVISED_VALIDATION', n, d))
        log('--artifact', BASE/'validation_hands.jsonl')
        execution['status'] = 'AUDITING_COLLECTION'
        write('execution.json', execution)
        train_audit = audit_trace(BASE/'training_hands.jsonl', seed=2026101501, hands=TRAIN_HANDS, teacher_count=TEACHERS,
                                  reservoir=reservoir, models=models, model_replay_hands=64)
        valid_audit = audit_trace(BASE/'validation_hands.jsonl', seed=2026101502, hands=VALID_HANDS, teacher_count=TEACHERS)
        assert training['decisions'] == train_audit['decisions'] and validation['decisions'] == valid_audit['decisions']
        write('collection_audit.json', dict(status='PASS', training=train_audit, validation=valid_audit,
              new_training_hands=TRAIN_HANDS, supervised_validation_hands=VALID_HANDS, reservoir_rows=len(reservoir),
              strength_evaluation_hands=0, slumbot_hands=0))
        verify(copies, inputs)
        del models
        torch.cuda.empty_cache()
        execution['status'] = 'SUPERVISED_FIT'
        write('execution.json', execution)
        fit = fit_student(inputs, reservoir)
        verify(copies, inputs)
        write('completed_analysis.json', dict(status='COMPLETED_PENDING_REVIEW', fit=fit,
              new_training_hands=TRAIN_HANDS, supervised_validation_hands=VALID_HANDS, strength_evaluation_hands=0,
              slumbot_hands=0, qualification_hands=0, goal_achieved=False, wall_time_seconds=time.time()-start))
        success = True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        log('--artifact', BASE/'failure.txt')
        failed = preserved_failure_accounting(execution['status'])
        write('failed_accounting.json', failed)
        execution['new_training_hands'] = failed['preserved_complete_raw_lines']['training']
        execution['supervised_validation_hands'] = failed['preserved_complete_raw_lines']['validation']
        log('--artifact', BASE/'failed_accounting.json', '--note', 'Failed-run counters are preserved complete raw hand claims, not proof of exact actual totals. Any unserialized in-flight barrier remains explicitly unknown; never automatically regenerate it.')
        print(traceback.format_exc(), flush=True)
    finally:
        execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',
                         finished_at=datetime.now(timezone.utc).isoformat(), wall_time_seconds=time.time()-start)
        write('execution.json', execution)
        artifacts = [p for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json', 'code.patch', 'source_manifest.json')]
        log(*[v for p in artifacts for v in ('--artifact', p)], '--count', f'new_training_hands={execution["new_training_hands"]}',
            '--count', f'evaluation_hands={execution["supervised_validation_hands"]}', '--count', 'slumbot_hands=0')
        print(json.dumps(execution), flush=True)
    if not success:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
