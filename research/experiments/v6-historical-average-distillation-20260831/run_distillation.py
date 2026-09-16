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
TRAIN = ROOT/'research/experiments/v6-selfplay75-transfer-pilot-r4-20260831'
EXTERNAL = ROOT/'research/experiments/v6-selfplay-transfer-fresh40k-slumbot-20260831'
CORPUS = ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01/states.jsonl'
SOURCE_SHA = '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
FINAL_SHA = 'a3f4f21eb7a0eb0e6bcaeb4929f06951ed1ac0bd74c0afd1920f5320e386d553'
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
    for row in copies:
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ('original', 'copy'))
    for row in inputs['teachers']:
        assert sha(row['source']) == sha(row['path']) == row['sha256']
    for row in inputs['dependencies']:
        assert sha(row['path']) == row['sha256']


def freeze_teachers():
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    assert read(EXTERNAL/'experiment.json')['status'] == 'COMPLETED'
    assert read(EXTERNAL/'reviewed_analysis.json')['decision'] == 'NEITHER_PILOT_POINT_POSITIVE'
    assert read(TRAIN/'experiment.json')['status'] == 'COMPLETED'
    assert read(TRAIN/'reviewed_analysis.json')['decision'] == 'ADMIT_FIXED_EXTERNAL_TRANSFER_PAIR'
    assert sha(CORPUS) == 'da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d'
    metrics = [json.loads(line) for line in (TRAIN/'production/control25/h1_training_metrics.jsonl').read_text().splitlines()]
    by_iteration = {r['iteration']: r['environment_hand_accounting']['completed_hands'] for r in metrics}
    available = []
    for path in (TRAIN/'production/control25/checkpoints').glob('*.pt'):
        m = re.fullmatch(r'checkpoint_iter(\d+)_hands(\d+)\.pt', path.name)
        if m:
            iteration = int(m[1])
            archived = torch.load(path, map_location='cpu', weights_only=False)
            actual = archived['environment_hand_accounting']['completed_hands']
            assert archived['iteration'] == iteration and archived['total_hands'] == int(m[2])
            assert by_iteration[iteration] <= actual < by_iteration.get(iteration+1, actual+1)
            available.append((actual, iteration, path))
    available.append((by_iteration[max(by_iteration)], max(by_iteration), TRAIN/'frozen/control25.pt'))
    available.sort()
    selected = [(0, 0, 0, TRAIN/'frozen/anchor0.pt')]
    for knot in range(65536, 1048577, 65536):
        hands, iteration, path = next(r for r in available if r[0] >= knot)
        selected.append((knot, hands, iteration, path))
    assert len(selected) == 17 and len({str(r[3]) for r in selected}) == 17
    (BASE/'teachers').mkdir()
    teachers = []
    for index, (knot, hands, iteration, path) in enumerate(selected):
        ck = torch.load(path, map_location='cpu', weights_only=False)
        validate_metadata(ck)
        assert len(ck['model']) == 86 and all(torch.isfinite(v).all() for v in ck['model'].values())
        if index:
            assert ck['iteration'] == iteration and ck['environment_hand_accounting']['completed_hands'] == hands
            assert ck['config']['self_play_fraction'] == .25
        target = BASE/'teachers'/f'teacher{index:02d}.pt'
        shutil.copy2(path, target)
        teachers.append(dict(index=index, knot=knot, original_physical_hands=hands, original_iteration=iteration,
                             source=str(path), path=str(target), sha256=sha(target), probability=1/17))
    assert teachers[0]['sha256'] == SOURCE_SHA and teachers[-1]['sha256'] == FINAL_SHA
    dependencies = [dict(path=str(p), sha256=sha(p)) for p in (CORPUS, TRAIN/'reviewed_analysis.json', EXTERNAL/'reviewed_analysis.json', TRAIN/'production/control25/h1_training_metrics.jsonl')]
    result = dict(teachers=teachers, dependencies=dependencies, collection_hands=TRAIN_HANDS,
                  supervised_validation_hands=VALID_HANDS, slumbot_hands=0, source_training_hands_recounted=0)
    write('input_manifest.json', result)
    log('--artifact', BASE/'input_manifest.json', *[v for r in teachers for v in ('--artifact', r['path'])])
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
    result = dict(status='PASS', teachers=17, states_per_teacher=64, policy_state_queries=17*64*3,
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
    torch.manual_seed(2026101004)
    torch.cuda.manual_seed_all(2026101004)
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
    generator = np.random.default_rng(2026101004)
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
        for epoch in range(1, 13):
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
            if epoch in (1, 4, 12):
                current = losses()
                summary = dict(epoch=epoch, step=steps, training_ce=total_loss/count, validation_ce=float(current.mean()))
                history.append(summary)
                print(json.dumps(summary), flush=True)
                np.save(BASE/f'validation_epoch{epoch:02d}_ce.npy', current)
            assert all(torch.isfinite(v).all() for v in student.state_dict().values())
            checkpoint = dict(**METADATA, model={k: v.detach().cpu().clone() for k, v in student.state_dict().items()},
                optimizer=optimizer.state_dict(), config={**source.get('config', {}), 'training_algorithm':'historical_behavior_distillation_v1',
                'lr':1e-4, 'seed':2026101004}, critic_contract=source.get('critic_contract', 'critic_v2'),
                norm_layer='gn', separate_preflop_head=True, epoch=epoch, iteration=epoch, total_hands=TRAIN_HANDS,
                optimizer_steps=steps, run_id=BASE.name, training_algorithm='historical_behavior_distillation_v1',
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
            if epoch in (1, 4, 12):
                shutil.copy2(BASE/'latest.pt', BASE/'checkpoints'/f'epoch{epoch:02d}.pt')
            write('fit_progress.json', dict(epoch=epoch, optimizer_steps=steps, fixed_final_epoch=12))
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
    result = dict(status='PASS', epochs=12, optimizer_steps=steps, trainable_changed_parameters=changed,
        frozen_value_parameters=[k for k in initial if k.startswith('value_head.')], source_ce=float(baseline.mean()),
        final_ce=float(final.mean()), hand_mean_ce_improvement=mean, hand_ci95=[mean-1.96*se, mean+1.96*se],
        history=history, model_sha256=sha(BASE/'latest.pt'), new_training_hands=TRAIN_HANDS,
        supervised_validation_hands=VALID_HANDS, validation_decisions=len(val_targets),
        decision='ADMIT_SEPARATE_STRENGTH_DIAGNOSTIC' if mean-1.96*se > 0 else 'HISTORICAL_FIT_GATE_NOT_PASSED')
    write('fit_analysis.json', result)
    return result


def main():
    import psutil
    import torch
    if sys.argv[1:] or any((BASE/name).exists() for name in ('execution.json', 'execution_code', 'teachers', 'training_hands.jsonl')):
        raise ValueError('No collector restart/resume/overwrite')
    for process in psutil.process_iter(['name', 'cmdline']):
        if process.pid != os.getpid() and (process.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ('train_v5.py', 'run_transfer.py', 'run_distillation.py', 'v6_mirror_eval.py', 'play_slumbot_v6_journaled.py') for a in process.info['cmdline'] or []):
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
        reservoir = Reservoir(262144, 2026101003)
        def progress(phase, completed, decisions):
            key = 'new_training_hands' if phase == 'TRAINING_DATA' else 'supervised_validation_hands'
            execution.update(status=phase, **{key: completed}, decisions_in_phase=decisions, wall_time_seconds=time.time()-start)
            write('execution.json', execution)
            log('--count', f'new_training_hands={execution["new_training_hands"]}', '--count', f'evaluation_hands={execution["supervised_validation_hands"]}',
                '--count', f'supervised_validation_hands={execution["supervised_validation_hands"]}')
            print(json.dumps(dict(phase=phase, completed_hands=completed, decisions=decisions)), flush=True)
        training = collect(models, seed=2026101001, hands=TRAIN_HANDS, out=BASE/'training_hands.jsonl', reservoir=reservoir,
                           progress=lambda n, d: progress('TRAINING_DATA', n, d))
        torch.save(reservoir.state_dict(), BASE/'reservoir.pt')
        log('--artifact', BASE/'reservoir.pt', '--artifact', BASE/'training_hands.jsonl')
        validation = collect(models, seed=2026101002, hands=VALID_HANDS, out=BASE/'validation_hands.jsonl',
                             progress=lambda n, d: progress('SUPERVISED_VALIDATION', n, d))
        log('--artifact', BASE/'validation_hands.jsonl')
        execution['status'] = 'AUDITING_COLLECTION'
        write('execution.json', execution)
        train_audit = audit_trace(BASE/'training_hands.jsonl', seed=2026101001, hands=TRAIN_HANDS, teacher_count=17,
                                  reservoir=reservoir, models=models, model_replay_hands=64)
        valid_audit = audit_trace(BASE/'validation_hands.jsonl', seed=2026101002, hands=VALID_HANDS, teacher_count=17)
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
