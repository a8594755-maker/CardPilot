"""Review saved raw validation evidence, then close this infrastructure record."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import sha256_file


def main():
    if sys.argv[1:]:
        raise ValueError('No alternative evidence directory')
    out = BASE/'reviewed_analysis.json'
    if out.exists():
        raise ValueError('Preserve existing review; no overwrite')
    final = BASE/'final01'
    analysis = json.loads((final/'analysis.json').read_text())
    assert analysis['status'] == 'PASS' and analysis['completed_validation_hands'] == 4096
    assert analysis['network_attempts'] == 0
    rows = [json.loads(line) for line in (final/'hands.jsonl').read_text().splitlines()]
    assert len(rows) == 4096
    assert sha256_file(final/'hands.jsonl') == analysis['hands_sha256']
    for index, row in enumerate(rows):
        assert row['hand_index'] == index and row['checked_decisions'] == len(row['actions'])
        assert len(row['deck']) == 52 and set(row['deck']) == set(range(52))
        assert len(row['payoffs_chips']) == 2 and sum(row['payoffs_chips']) == 0
        assert all(type(v) is int and -20000 <= v <= 20000 for v in row['payoffs_chips'])
    events = [json.loads(line) for line in (final/'events.jsonl').read_text().splitlines()]
    cursor = 0
    for index, row in enumerate(rows):
        assert events[cursor] == dict(hand_index=index, deck=row['deck'])
        cursor += 1
        for action in row['actions']:
            assert events[cursor] == dict(hand_index=index, action=action)
            cursor += 1
    assert cursor == len(events)
    assert sum(row['checked_decisions'] for row in rows) == analysis['checked_decisions']
    copies = json.loads((final/'execution_code/copy_manifest.json').read_text())
    for item in copies:
        for key in ['original', 'copy']:
            assert sha256_file(ROOT/item[key]) == item['sha256'], item
    vendor = json.loads((final/'oracle_source_hashes.json').read_text())
    for relative, digest in vendor.items():
        assert sha256_file(BASE/relative) == digest
    suites = ET.parse(final/'tests.xml').getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in suites) == 88
    assert sum(int(s.attrib.get(k, 0)) for s in suites for k in ['errors', 'failures', 'skipped']) == 0
    prior = ROOT/'research/experiments/native-state-contract-audit-20260831/execution_code/copy_manifest.json'
    historical = {item['original']: item for item in json.loads(prior.read_text())}
    preserved = ['scripts/deep_cfr/game_state.py', 'scripts/alpha_holdem/environment.py',
                 'scripts/alpha_holdem/environment_v55.py', 'scripts/alpha_holdem/play_slumbot.py',
                 'scripts/alpha_holdem/v5_mirror_eval.py']
    for relative in preserved:
        assert sha256_file(ROOT/relative) == historical[relative]['sha256']
    policy_paths = {
        'models/baseline/standard10/latest.pt': '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
        'research/experiments/matched-weak-kl-representation-curve-20260830/frozen/full.pt': 'ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e',
        'research/experiments/matched-weak-kl-representation-curve-20260830/frozen/heads.pt': 'ebfc850cb8ed92c07103bbb92a8b473433a63c6df173c0f002741c560b84e63b',
    }
    for relative, digest in policy_paths.items():
        assert sha256_file(ROOT/relative) == digest
    streets = Counter(st for row in rows for st in row['streets_seen'])
    summary = dict(status='PASS', decision='V6_CONTRACT_REPAIR_VALIDATED',
        final_validation_hands=4096, checked_decisions=analysis['checked_decisions'], tests_passed=88,
        source_pairs_verified=len(copies), oracle_source_files_verified=len(vendor),
        legacy_runtime_files_preserved=preserved, frozen_policies_preserved=policy_paths,
        prior_core_validation_hands=4096, unique_fixed_validation_deals=4096,
        repeated_validation_not_independent=True, hands_reaching_decision_by_street=dict(streets),
        showdown_hands=sum(row['folded'] == -1 for row in rows),
        history_overflow_hands=sum(row['max_prior_actions_on_one_street'] >= 6 for row in rows),
        maximum_prior_actions_on_street=max(row['max_prior_actions_on_one_street'] for row in rows),
        raw_events=len(events), new_training_hands=0, evaluation_hands=0, slumbot_hands=0,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        scope_limitations=['No optimizer update or full training CLI smoke yet',
            'No live Slumbot traffic; new transport wrapper requires benchmark-specific evidence audit before100k',
            'First-six-per-street history truncation retained with correct street identity',
            'Legacy ELO tournament and unversioned offline replay rejected in v6',
            'Legacy weights require explicitly recorded new-contract rebinding; old results do not transfer'])
    out.write_text(json.dumps(summary, indent=2)+'\n')
    report = BASE/'result_summary.md'
    report.write_text(
        '# V6 contract repair validated\n\n'
        f'Final frozen-source validation:4096 hands, {analysis["checked_decisions"]} decisions, '
        '88 passing tests. Integer-chip transitions match independent PokerKit0.7.5; '
        'every decision matches external-prefix reconstruction, and canonical history/cards '
        'match independent client encoders. BB option, full minimum raises, short all-ins, '
        'no raise cap, chip conservation, zero-sum terminal payoff and history overflow tested.\n\n'
        f'Raw event/hand evidence aligns exactly; {len(copies)} source/copy pairs and '
        f'{len(vendor)} oracle source hashes verified. Five legacy runtime files and three '
        'frozen policies remain unchanged. Trainer changes are explicit v6 branches; '
        'new v6 mirror and deployment use the same inference/action contract.\n\n'
        'core01 and final01 reuse the same4096 fixed deals:8192 executed validation trajectories, '
        'not8192 independent samples. Pytest fixtures are synthetic/regression checks, not '
        'strength data. Training/evaluation/Slumbot accounting is zero. Development failure '
        'reports01(card formatting) and03(test import path) are retained alongside passes02/04/05.\n\n'
        'Next: separately preregister a small measured-physical-hand v6 trainer smoke, verify '
        'actual optimizer/checkpoint/worker accounting, then establish corrected-environment '
        'frozen multi-anchor baselines and a learned-weight curve. No positive-strength claim '
        'or100k admission follows from infrastructure tests. Legacy ELO and unversioned '
        'offline replay remain blocked pending their own v6 contracts.\n')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
        '--command', 'python research/experiments/native-rules-contract-repair-20260831/review_and_finish.py',
        '--artifact', str(Path(__file__)), '--artifact', str(out), '--artifact', str(report),
        '--metric', 'final_validation_hands=4096', '--metric', f'checked_decisions={analysis["checked_decisions"]}',
        '--metric', 'tests_passed=88', '--metric', 'executed_oracle_validation_hands=8192',
        '--metric', 'unique_fixed_validation_deals=4096',
        '--note', 'Read-only raw-event/hand/source review passed. Only infrastructure readiness established; no actual optimizer update or live benchmark. Next work is a separately recorded v6 training smoke.'], check=True)
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name,
        '--status', 'COMPLETED', '--summary',
        'Versioned integer-chip v6 passed88tests and4096fixed independent-oracle hands with34159per-decision contract checks; zero training or Slumbot.',
        '--conclusion', 'The five reproduced discrepancies are repaired in explicitv6 execution paths. Legacy sources/results remain reproducible; positive learned strength is not established.',
        '--decision', 'V6_CONTRACT_REPAIR_VALIDATED', '--next-step',
        'Preregister a bounded actual v6 training smoke, verify optimizer and physical counters, then establish corrected-contract baseline/learning curves without pooling legacy results.',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0'], check=True)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
