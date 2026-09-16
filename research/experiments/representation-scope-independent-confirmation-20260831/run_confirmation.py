"""Fixed independent confirmation of the admitted representation-scope final endpoints."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
ID = BASE.name
PARENT = ROOT/'research/experiments/matched-weak-kl-representation-curve-20260830'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PARENT))
from run_pilot import ANCHORS, DIGESTS, sha
from report_completed_pilot import compare, admission, assert_contrasts_match
from raw_cell_review import review_cell
from research.experiment_log import capture_code_provenance

SEED, PAIRS = 20260913, 8192
MODE, RNG = 'sampled_both_sides', 'sha256_seed_pair_physical_seat_decision_v1'
NAMES = ['standard10', 'slumbot_free', 'corrected_cfr96', 'heldout_weak']
CANDIDATES = [
    ('source', ANCHORS[0], DIGESTS[0]),
    ('heads', PARENT/'frozen/heads.pt', 'ebfc850cb8ed92c07103bbb92a8b473433a63c6df173c0f002741c560b84e63b'),
    ('full', PARENT/'frozen/full.pt', 'ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e')]
PARENT_ANALYSIS_SHA = '6604dc6f9b827b475c15e8e41e49b20740de974c35b071dc0e65aa623a9df690'


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID, *map(str, args)], cwd=ROOT, check=True)


def record_command(command):
    log('--command', subprocess.list2cmdline(['python', *map(str, command)]))


def validate_cell(doc, execution, digest, pairs=PAIRS):
    expected = dict(seed=SEED, pairs=pairs, starting_stack=200., policy_mode=MODE, action_rng_schema=RNG)
    if any(doc.get(k) != v for k, v in expected.items()):
        raise ValueError('Confirmation configuration mismatch')
    if execution.get('status') != 'COMPLETED' or doc['execution'].get('status') != 'COMPLETED':
        raise ValueError('Incomplete cell execution')
    if doc['candidate']['sha256'] != digest or len(doc['anchors']) != 4:
        raise ValueError('Wrong candidate identity or anchor count')
    for i, row in enumerate(doc['anchors']):
        if row['anchor'] != NAMES[i] or row['anchor_sha256'] != DIGESTS[i]:
            raise ValueError('Wrong anchor identity/order')
        if row.get('action_rng') != dict(schema=RNG, seed=SEED+i*1000003):
            raise ValueError('Wrong paired action stream')
        if type(row['pairs']) is not int or row['pairs'] != pairs or row['hands'] != 2*pairs:
            raise ValueError('Wrong pair/hand count')
        if any(len(row['paired_outcomes'][k]) != pairs for k in ['overall_bb_per_hand', 'bb_bb_per_hand', 'sb_bb_per_hand']):
            raise ValueError('Incomplete raw outcomes')
    review_cell(doc)
    return 8*pairs


def ensure_idle():
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if p.pid == psutil.Process().pid or not (p.info['name'] or '').lower().startswith('python'):
            continue
        args = p.info['cmdline'] or []
        if any(Path(a).name in ['train_v5.py', 'v5_mirror_eval.py', 'play_slumbot.py', 'run_confirmation.py', 'run_pilot.py'] for a in args):
            raise RuntimeError('Another training/evaluation writer is live')


def verify_inputs():
    parent = json.loads((PARENT/'experiment.json').read_text())
    analysis = json.loads((PARENT/'completed_analysis.json').read_text())
    if parent['status'] != 'COMPLETED' or analysis['decision'] != 'REPRESENTATION_SCOPE_ADMITS_CONFIRMATION':
        raise ValueError('Completed admitted parent required')
    if sha(PARENT/'completed_analysis.json') != PARENT_ANALYSIS_SHA:
        raise ValueError('Reviewed parent analysis changed')
    for _, path, digest in CANDIDATES:
        if sha(path) != digest:
            raise ValueError('Frozen candidate changed')
    for path, digest in zip(ANCHORS, DIGESTS):
        if sha(path) != digest:
            raise ValueError('Frozen anchor changed')


def verify_sources(items):
    for row in items:
        if sha(ROOT/row['original']) != row['sha256'] or sha(ROOT/row['copy']) != row['sha256']:
            raise ValueError('Execution source changed')


def snapshot():
    folder = BASE/'execution_code'
    folder.mkdir(exist_ok=False)
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py']
    paths += [(PARENT/f'{n}.py').relative_to(ROOT).as_posix() for n in ['run_pilot', 'evaluate', 'report_completed_pilot', 'raw_cell_review', 'test_completed_report']]
    paths += [(BASE/f'{n}.py').relative_to(ROOT).as_posix() for n in ['run_confirmation', 'test_confirmation', 'finish_confirmation']]
    paths += [(BASE/'preregistration.md').relative_to(ROOT).as_posix()]
    capture_code_provenance(ROOT, folder, paths)
    copies = []
    for relative in paths:
        target = folder/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    (folder/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    verify_sources(copies)
    log(*[x for n in ['copy_manifest.json', 'source_manifest.json', 'code.patch'] for x in ['--artifact', str(folder/n)]])
    return folder, copies


def analyze(documents):
    comparisons = {f'{t}_vs_{c}': compare(documents[c], documents[t]) for c, t in
                   [('heads', 'full'), ('source', 'full'), ('source', 'heads')]}
    passed = admission(comparisons['full_vs_heads'], comparisons['full_vs_source'])
    return dict(status='PASS', evaluation_hands=196608, new_training_hands=0, slumbot_hands=0,
        seed=SEED, pairs_per_anchor=PAIRS, comparisons=comparisons, replication_passed=passed,
        decision='REPRESENTATION_SCOPE_REPLICATION_PASSED' if passed else 'REPRESENTATION_SCOPE_REPLICATION_NOT_ADMITTED',
        parent_discovery_hands_excluded=163840, claim_scope='independent_internal_not_slumbot',
        limitations=['Independent deal/action randomness, not an independent training seed.',
            'Three anchors were training opponents; fourth was excluded only from the current training run and shares historical source/league lineage.',
            'Normal paired CIs and a four-primary-contrast Bonferroni gate; no discovery pooling.',
            'Passing admits only a separately preregistered fixed20k Slumbot pilot, not100k qualification.'])


def validate_paired_output(stored, control_hash, treatment_hash, rows):
    # control/treatment are the external tool's schema keys, not policy labels.
    if (stored['control']['sha256'] != control_hash
            or stored['treatment']['sha256'] != treatment_hash):
        raise ValueError('Paired analysis input hash mismatch')
    names = [row['anchor'] for row in stored['anchors']]
    if len(names) != len(NAMES) or set(names) != set(NAMES):
        raise ValueError('Paired output anchor count/identity mismatch')
    if [row['anchor'] for row in rows] != NAMES:
        raise ValueError('Independent comparison anchor count/order mismatch')
    external_rows = {row['anchor']: row for row in stored['anchors']}
    for row in rows:
        external = external_rows[row['anchor']]
        for local_key, external_key in [('delta_bb100', 'treatment_minus_control_bb100'),
                                        ('ci95_half_width', 'paired_ci95_bb100')]:
            value = external[external_key]
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not math.isclose(row[local_key], value, abs_tol=1e-8, rel_tol=1e-10)):
                raise ValueError('Independent raw comparison disagrees')


def main():
    if sys.argv[1:]:
        raise ValueError('No automatic resume or parameter overrides')
    ensure_idle()
    if json.loads((BASE/'experiment.json').read_text())['status'] != 'RUNNING':
        raise ValueError('A RUNNING preregistered record is required')
    if any((BASE/n).exists() for n in ['execution_code', 'matrix', 'replication_analysis.json']):
        raise ValueError('Preserve existing evidence; no automatic restart')
    verify_inputs()
    folder, copies = snapshot()
    record_command([str(Path(__file__).relative_to(ROOT))])
    script = folder/'source_files/scripts/alpha_holdem/v5_mirror_eval.py'
    matrix = BASE/'matrix'
    matrix.mkdir(exist_ok=False)
    documents, paths, hands = {}, {}, 0
    for label, checkpoint, digest in CANDIDATES:
        verify_inputs()
        verify_sources(copies)
        out, md, execution, stdout = [matrix/f'{label}{s}' for s in ['.json', '.md', '_execution.json', '_stdout.log']]
        command = [str(script), '--candidate', str(checkpoint), '--candidate-label', f'representation_confirmation_{label}',
            '--policy-mode', MODE, '--pairs', str(PAIRS), '--starting-stack', '200', '--seed', str(SEED),
            '--include-pair-outcomes', '--device', 'cuda', '--priority', 'below-normal',
            '--out-json', str(out), '--out-md', str(md), '--execution-json', str(execution)]
        for name, path in zip(NAMES, ANCHORS): command += ['--anchor', f'{name}={path}']
        record_command(command)
        with stdout.open('x', encoding='utf-8') as handle:
            subprocess.run([sys.executable, *command], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, check=True)
        doc = json.loads(out.read_text())
        hands += validate_cell(doc, json.loads(execution.read_text()), digest)
        documents[label], paths[label] = doc, out
        verify_inputs()
        verify_sources(copies)
        log('--count', f'evaluation_hands={hands}', *[x for p in [out, md, execution, stdout, checkpoint] for x in ['--artifact', str(p)]])
    result = analyze(documents)
    for label, c, t in [('full_vs_heads', 'heads', 'full'), ('full_vs_source', 'source', 'full'), ('heads_vs_source', 'source', 'heads')]:
        out = matrix/f'{label}.json'
        command = [str(folder/'source_files/scripts/alpha_holdem/paired_mirror_treatment_delta.py'),
                   '--control', str(paths[c]), '--treatment', str(paths[t]), '--out', str(out)]
        record_command(command)
        subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
        stored = json.loads(out.read_text())
        validate_paired_output(stored, sha(paths[c]), sha(paths[t]), result['comparisons'][label])
        log('--artifact', str(out))
    if hands != 196608: raise ValueError('Wrong total evaluation hands')
    result['cell_hashes'] = {label: sha(path) for label, path in paths.items()}
    result['candidate_hashes'] = {label: digest for label, _, digest in CANDIDATES}
    verify_inputs()
    verify_sources(copies)
    out = BASE/'replication_analysis.json'
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    log('--artifact', str(out), '--metric', 'replication_complete=1', '--metric', f'replication_passed={int(result["replication_passed"])}',
        '--note', 'Fixed independent matrix completed. Raw pair/seat and OOD statistics, independent paired-CI recomputation and frozen source/model hashes passed. Await post-exit review before finish; no Slumbot success claim.')
    print(json.dumps(dict(decision=result['decision'], evaluation_hands=hands)))


if __name__ == '__main__':
    main()
