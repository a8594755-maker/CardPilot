"""Continue only the untouched 4M evaluation after the capped-history proof."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE))
import run_guarded_followthrough as old
from audit_pool_history_windows import ORIGINAL_SHA, require

REL = str(BASE.relative_to(ROOT)).replace('\\', '/')
POOL_SHA = '3409300bf825a45aae9559c580a83ce67e732cce64425c2fa41dc326f0770586'


def load(path):
    return json.loads(Path(path).read_text())


def validate_proofs(original, pool, mechanics):
    require([row['name'] for row in original['runs']] == ['seed1', 'seed2', 'seed3'], 'original seed set')
    require(pool['passed'] is True and mechanics['posthoc_observed_mechanics_passed'] is True,
            'pool and independent mechanics proofs required')
    require([row['name'] for row in pool['runs']] == ['seed1', 'seed2', 'seed3'], 'pool seed set')
    require([row['name'] for row in mechanics['runs']] == ['seed1', 'seed2', 'seed3'], 'mechanics seed set')
    expected = [{'dynamic_pool_healthy'},
                {'dynamic_pool_healthy', 'corrected_legacy_contract_bound', 'physical_accounting_exact', 'resume_controls_exact'},
                {'dynamic_pool_healthy', 'corrected_legacy_contract_bound'}]
    for index, (run, pool_run, mech) in enumerate(zip(original['runs'], pool['runs'], mechanics['runs'], strict=True)):
        require({key for key, value in run['gates'].items() if value is not True} == expected[index],
                'unrelated original audit failure or changed original gates')
        require(pool_run['passed'] is True and mech['posthoc_observed_mechanics_passed'] is True,
                'unqualified endpoint')
        require(pool_run['checkpoint_sha256'] == run['hashes']['checkpoint']
                == mech['generic_audit']['hashes']['checkpoint'], 'endpoint proof hash mismatch')
        require(len(mech['segments']) == (3 if index == 1 else 1), 'missing recovery segment proof')
        require(all(segment['passed'] and all(segment['gates'].values()) for segment in mech['segments']),
                'failed recovery segment')
    require(all(value is True for value in original['session_independence'].values()),
            'original session independence failure')


def preflight():
    prior = BASE / 'guarded_followthrough_v1'
    ownership, state = load(prior / 'ownership.json'), load(prior / 'status.json')
    require(state['phase'] == 'STOPPED_FOR_RESEARCHER_ATTENTION' and state['active_child_pid'] is None,
            'original owner not at the observed stopped boundary')
    require(state['error'] == "RuntimeError: unrelated original audit failure: seed1 ['dynamic_pool_healthy']",
            'another original stopping condition')
    for identity in ownership['waited_processes'] + [ownership]:
        require(not old.same_process_live(identity), 'original process identity still live')
    forbidden = {'train_v5.py', 'train_v5_managed_candidate.py', 'v6_public_opponent_matched_eval.py',
                 'v6_legacy_bridge_drift_audit.py', 'audit_frozen_endpoints.py', 'audit_pool_history_windows.py'}
    for process in psutil.process_iter(['pid', 'cmdline']):
        require(not any(Path(value).name in forbidden for value in process.info.get('cmdline') or []),
                f'other poker trainer/evaluator/auditor live: {process.pid}')
    audit_path, pool_path = BASE / 'training_audit.json', BASE / 'pool_history_window_audit.json'
    mechanics_path = BASE / 'frozen_allseed_mechanics_inherited_bridge.json'
    require(old.sha(audit_path) == ORIGINAL_SHA and old.sha(pool_path) == POOL_SHA, 'original/scoped proof changed')
    original, pool, mechanics = load(audit_path), load(pool_path), load(mechanics_path)
    validate_proofs(original, pool, mechanics)
    frozen = dict(ownership['frozen_sources'])
    for mapping in (load(prior / 'frozen_evaluation_inputs.json'), pool['input_sha256']):
        for path, digest in mapping.items():
            require(path not in frozen or frozen[path] == digest, 'conflicting frozen hash binding')
            frozen[path] = digest
    for path in (Path(__file__), prior / 'ownership.json', prior / 'status.json',
                 audit_path, pool_path, mechanics_path, BASE / 'pool_qualified_followthrough_contract.md'):
        frozen[str(path.resolve())] = old.sha(path)
    for path, digest in frozen.items():
        require(old.sha(path) == digest, f'frozen dependency changed: {path}')
    for seed in (1, 2, 3):
        require(load(BASE / f'seed{seed}/run_manifest.json')['status'] == 'finished', 'unfinished trainer manifest')
        for prefix in ('eval', 'drift'):
            require(not (BASE / f'{prefix}_seed{seed}').exists(), 'refuse existing evaluation evidence')
    for name in ('aggregate.json', 'deviation_aware_report.json'):
        require(not (BASE / name).exists(), 'refuse existing aggregate evidence')
    return frozen, ownership


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    frozen, prior_owner = preflight()
    if args.preflight_only:
        print(json.dumps({'passed': True, 'new_hands': 0, 'frozen_inputs': len(frozen),
                          'evaluation_started': False}))
        return
    directory = BASE / 'guarded_followthrough_v2_pool_qualified'
    directory.mkdir()
    owner = {'pid': os.getpid(), 'create_time': psutil.Process().create_time(), 'frozen_sources': frozen,
             'previous_owner': prior_owner, 'scope': 'unchanged 4M evaluation only; no new training'}
    (directory / 'ownership.json').write_text(json.dumps(owner, indent=2) + '\n')
    phase, child = 'PREREGISTERED_FROZEN_EVALUATION', None

    def status(**extra):
        value = {'phase': phase, 'pid': os.getpid(), 'at': datetime.now(timezone.utc).isoformat(),
                 'active_child_pid': child.pid if child is not None and child.poll() is None else None, **extra}
        pending = directory / 'status.pending.json'
        pending.write_text(json.dumps(value, indent=2) + '\n')
        os.replace(pending, directory / 'status.json')
        print(json.dumps(value), flush=True)

    def update(note='', artifact=None, command=None):
        argv = [sys.executable, 'research/experiment_log.py', 'update', BASE.name,
                '--count', 'new_training_hands=6291386', '--count', 'environment_training_hands=6291386',
                '--count', 'lineage_training_hands=12588188',
                '--count', f'evaluation_hands={old.evidenced_evaluation_hands()}',
                '--metric', f'guarded_pipeline_phase={json.dumps(phase)}']
        if note:
            argv += ['--note', note]
        if artifact:
            argv += ['--artifact', str(artifact)]
        if command:
            argv += ['--command', subprocess.list2cmdline(command)]
        subprocess.run(argv, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

    def step(name, argv, artifact, allowed=(0,)):
        nonlocal child
        for path, digest in frozen.items():
            require(old.sha(path) == digest, f'frozen dependency changed: {path}')
        require(not artifact.exists(), 'refuse repeated completed step')
        command_path = directory / f'{name}.command.json'
        command_path.write_text(json.dumps(argv, indent=2) + '\n')
        update(artifact=command_path, command=argv)
        with (directory / f'{name}.stdout.log').open('x', encoding='utf-8') as log:
            child = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                     env=dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
            status(active_command=name, child_create_time=psutil.Process(child.pid).create_time())
            last_update = time.monotonic()
            while child.poll() is None:
                time.sleep(5)
                if time.monotonic() - last_update >= 60:
                    update()
                    last_update = time.monotonic()
            require(child.returncode in allowed, f'{name} exited {child.returncode}; preserve all evidence')
            child = None
        require(artifact.exists(), 'required step artifact missing')
        update(artifact=artifact)

    try:
        status()
        update(note='New one-shot evaluation owner after the separately verified capped-history false failure. Original audit/status remain immutable. Full pool archive/assignment replay and independent endpoint/resume checks passed before any new evaluation. Original 3 seeds, four anchors, decks, both seats, budgets and production runtime remain unchanged. No competing writer or edits to this owner frozen inputs until terminal.', artifact=directory / 'ownership.json')
        for seed in (1, 2, 3):
            step(f'eval_seed{seed}', old.eval_argv(seed), BASE / f'eval_seed{seed}/summary.json')
        phase = 'PREREGISTERED_OFFLINE_DRIFT'
        for seed in (1, 2, 3):
            out = BASE / f'drift_seed{seed}'
            argv = [sys.executable, 'scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py',
                    '--parent', 'models/baseline/standard10/latest.pt', '--parent-sha256',
                    '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
                    '--treatment', f'{REL}/seed{seed}/latest.pt', '--out-dir', str(out),
                    '--states', '20000', '--seed', str(20263290 + seed), '--device', 'cuda',
                    '--batch-size', '1024', '--source-tv-max', '1', '--greedy-disagreement-max', '1']
            step(f'drift_seed{seed}', argv, out / 'drift_analysis.json')
        phase = 'DESCRIPTIVE_AGGREGATION_NO_AUTO_SCALE'
        aggregate = BASE / 'aggregate.json'
        argv = [sys.executable, 'scripts/alpha_holdem/aggregate_v6_static_current_kl_1m.py', '--experiment-dir', REL]
        for prior in ('v6-static-current-kl-262k-scale-20260903', 'v6-static-current-kl-262k-fresh-confirmation-20260903',
                      'v6-static-current-kl-1m-scale-20260903', 'v6-static-current-kl-2m-scale-20260904'):
            argv += ['--prior-dir', f'research/experiments/{prior}']
        argv += ['--expected-prior-raw-rows', '122880', '--eval-seed-base', '20263280', '--drift-seed-base', '20263290',
                 '--scale-label', '4M', '--schema', 'cardpilot.static_current_kl_4m_aggregate.v1',
                 '--breadth-informational-only', '--require-positive-combined', '--require-improved-breadth', '--out', str(aggregate)]
        step('original_aggregate', argv, aggregate, (0, 1))
        report = BASE / 'deviation_aware_report.json'
        step('deviation_report', [sys.executable, str(BASE / 'report_4m_deviation.py'), '--legacy-aggregate', str(aggregate),
             '--posthoc-mechanics', str(BASE / 'frozen_allseed_mechanics_inherited_bridge.json'), '--out', str(report)], report)
        phase = 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
        status(report=str(report), pool_proof=str(BASE / 'pool_history_window_audit.json'))
        update(note='All original evaluation and drift budgets completed after the bounded capped-history proof. All original failures and Seed2 freshness limitations remain preserved. Main researcher must analyze/finish the same record; no automatic training or scale.', artifact=report)
    except BaseException as error:
        phase = 'STOPPED_FOR_RESEARCHER_ATTENTION'
        status(error=f'{type(error).__name__}: {error}')
        update(note=f'Pool-qualified evaluation stopped; do not overwrite/restart evidence: {type(error).__name__}: {error}', artifact=directory / 'status.json')
        raise


if __name__ == '__main__':
    main()
