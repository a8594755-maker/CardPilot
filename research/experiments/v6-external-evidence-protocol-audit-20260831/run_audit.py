"""Fixed offline client-control-flow probes; never changes production source."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file

CASES = ['normal', 'opponent_fold', 'new_hand_first_error', 'new_hand_second_error',
         'act_first_error', 'act_second_error', 'noninteger_reward',
         'out_of_bounds_reward', 'midhand_token_rotation', 'premature_terminal']


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'),
                    'update', BASE.name, *map(str, args)], cwd=ROOT, check=True)


def main():
    if sys.argv[1:] or (BASE/'cases').exists() or (BASE/'execution_code').exists():
        raise ValueError('Fixed diagnostic; preserve existing outputs')
    started = time.time()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md', '.txt'}]
    directory = BASE/'execution_code'
    directory.mkdir()
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    log(*[v for name in ['source_manifest.json', 'code.patch', 'copy_manifest.json']
          for v in ['--artifact', directory/name]])
    import torch
    from alpha_holdem import play_slumbot_v6 as client
    from alpha_holdem.execution_v6 import external_decision
    from alpha_holdem.policy_contract_v6 import apply_incr
    from alpha_holdem.rules_v6 import ChipState
    from deep_cfr.hand_eval import card_to_str
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    class ToyPolicy(torch.nn.Module):
        def forward(self, cards, actions, extra, mask):
            logits = torch.zeros((len(cards), 9), dtype=torch.float32)
            logits[:, 1] = 100  # passive fixture policy, not a learned model
            return logits.masked_fill(mask == 0, -1e9), torch.zeros((len(cards), 1))

    model = ToyPolicy().eval()
    fixture = BASE/'toy_policy_fixture.txt'
    digest = sha256_file(fixture)
    original_play_one = client.play_one
    denied_calls = []

    def deny_network(*args, **kwargs):
        denied_calls.append('connection_attempt')
        raise AssertionError('External network forbidden in offline protocol diagnostic')

    class OfflineServer:
        def __init__(self, case):
            self.case, self.hand, self.calls, self.completed = case, 0, [], 0
            self.token = 'PUBLIC-OFFLINE-FIXTURE-TOKEN-A'
            self.state, self.text = None, ''

        def move(self, incr):
            old = self.state.street
            self.state = apply_incr(self.state, incr)
            self.text += incr
            if self.state.street > old and not self.state.terminal:
                self.text += '/'

        def response(self):
            seat = 0 if self.case == 'opponent_fold' else 1
            while not self.state.terminal and self.state.actor != seat:
                self.move('f' if self.case == 'opponent_fold' else ('c' if self.state.to_call else 'k'))
            result = dict(token=self.token, action=self.text, client_pos=seat,
                          hole_cards=[card_to_str(c) for c in self.state.holes[seat]],
                          board=[card_to_str(c) for c in self.state.board])
            if self.state.terminal:
                self.completed += 1
                result['winnings'] = self.state.payoffs()[seat]
                if self.case == 'noninteger_reward': result['winnings'] = 0.5
                if self.case == 'out_of_bounds_reward': result['winnings'] = 20001
            if self.case == 'premature_terminal': result['winnings'] = 123
            self.calls[-1]['response'] = result.copy()
            return result

        def new_hand(self, token):
            self.hand += 1
            self.calls.append(dict(method='new_hand', hand=self.hand, token=token))
            if self.case == 'new_hand_first_error' or (self.case == 'new_hand_second_error' and self.hand == 2):
                self.calls[-1]['error'] = 'simulated ambiguous request failure'
                raise ConnectionError('simulated ambiguous new_hand response loss')
            assert token == (None if self.hand == 1 else self.token)
            deck = list(range(52))
            random.Random(2026092000+self.hand).shuffle(deck)
            self.state, self.text = ChipState.new(deck), ''
            return self.response()

        def act(self, token, incr):
            self.calls.append(dict(method='act', hand=self.hand, token=token, increment=incr))
            assert token == self.token
            if self.case == 'act_first_error' or (self.case == 'act_second_error' and self.hand == 2):
                self.calls[-1]['error'] = 'simulated ambiguous request failure'
                raise ConnectionError('simulated ambiguous act response loss')
            self.move(incr)
            if self.case == 'midhand_token_rotation': self.token = 'PUBLIC-OFFLINE-FIXTURE-TOKEN-B'
            return self.response()

    results = []
    with patch.object(socket.socket, 'connect', deny_network), patch.object(socket, 'create_connection', deny_network):
        for case in CASES:
            case_dir = BASE/'cases'/case
            case_dir.mkdir(parents=True)
            output = case_dir/'client'
            server = OfflineServer(case)
            command = ['play_slumbot_v6.py', '--model', str(fixture), '--hands', '2',
                       '--seed', '20260920', '--out-dir', str(output), '--device', 'cpu']
            def fixture_play_one(m, token, rng, *, device='cpu'):
                return original_play_one(m, token, rng, device=device,
                                         new_hand_fn=server.new_hand, act_fn=server.act)
            captured, error = io.StringIO(), None
            with patch.object(client, 'load_policy', return_value=(model, {'fixture_only': True}, digest)), \
                 patch.object(client, 'play_one', fixture_play_one), \
                 patch.object(torch, 'set_num_threads'), patch.object(torch, 'set_num_interop_threads'), \
                 patch.object(sys, 'argv', command), redirect_stdout(captured):
                try: client.main()
                except Exception as exc: error = dict(type=type(exc).__name__, message=str(exc))
            (case_dir/'stdout.txt').write_text(captured.getvalue())
            (case_dir/'fixture_calls.json').write_text(json.dumps(server.calls, indent=2)+'\n')
            summary = json.loads((output/'summary.json').read_text())
            rows = [json.loads(line) for line in (output/'hands.jsonl').read_text().splitlines()]
            assert len(rows) == summary['successful_hands']
            assert (error is None) == (summary['status'] == 'COMPLETED')
            assert [r['successful_hand'] for r in rows] == list(range(1, len(rows)+1))
            assert sum(r['winnings_chips'] for r in rows) == summary['cumulative_chips']
            running = 0
            for row in rows:
                running += row['winnings_chips']
                assert row['model_sha256'] == digest and row['cumulative_chips'] == running
                assert row['winnings_bb'] == row['winnings_chips']/100
                for decision in row['decisions']:
                    incr, replay = external_decision(model, decision, uniform=decision['uniform'])
                    assert incr == decision['direct_increment'] and replay['behavior_probs'] == decision['behavior_probs']
            for p in output.iterdir():
                assert 'PUBLIC-OFFLINE-FIXTURE-TOKEN-' not in p.read_text()
            expected_count = 1 if case in {'new_hand_second_error', 'act_second_error'} else (
                0 if case in {'new_hand_first_error', 'act_first_error', 'noninteger_reward'} else 2)
            assert len(rows) == expected_count
            assert server.hand == (1 if case in {'new_hand_first_error', 'act_first_error', 'noninteger_reward'} else 2)
            if case in {'act_first_error', 'act_second_error'}:
                failed_hand = 1 if case == 'act_first_error' else 2
                assert sum(r['method']=='act' and r['hand']==failed_hand for r in server.calls) == 1
            result = dict(case=case, client_status=summary['status'], exception=error,
                          fixture_new_hand_attempts=server.hand, fixture_terminal_trajectories=server.completed,
                          client_completed_rows=len(rows), fixture_call_count=len(server.calls),
                          persisted_files=sorted(p.name for p in output.iterdir()),
                          journal_present=any('journal' in p.name or 'attempt' in p.name for p in output.iterdir()),
                          decisions_replayed=sum(len(r['decisions']) for r in rows),
                          raw_hand_sha256=sha256_file(output/'hands.jsonl'),
                          fixture_calls_sha256=sha256_file(case_dir/'fixture_calls.json'))
            (case_dir/'analysis.json').write_text(json.dumps(result, indent=2)+'\n')
            results.append(result)
    assert not denied_calls
    for item in copies:
        assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
    findings = [
        dict(id='missing_attempt_journal', evidence_cases=['new_hand_first_error', 'act_first_error', 'act_second_error'],
             detail='Only completed hands and aggregate summary persist; failed attempt/request intent and partial decision trace exist only in the diagnostic server transcript, not client artifacts.'),
        dict(id='terminal_bounds_not_enforced', evidence_cases=['out_of_bounds_reward'],
             detail='Integer winnings beyond the200bb zero-rake bound are accepted as completed hands; downstream evidence qualification must reject them.'),
        dict(id='terminal_history_not_validated', evidence_cases=['premature_terminal'],
             detail='Winnings on a nonterminal action prefix are accepted without a terminal-state consistency check.'),
        dict(id='token_transition_not_persisted', evidence_cases=['midhand_token_rotation'],
             detail='Client follows rotated tokens but only persists the initial token hash for each completed hand; no request-by-request transition evidence.'),
    ]
    report = dict(status='PASS', decision='V6_EXTERNAL_EVIDENCE_HARDENING_REQUIRED',
                  new_training_hands=0, evaluation_hands=0, slumbot_hands=0,
                  synthetic_cases=len(results), synthetic_terminal_trajectories=sum(r['fixture_terminal_trajectories'] for r in results),
                  decision_replays=sum(r['decisions_replayed'] for r in results), network_connections=0,
                  source_pairs_verified=len(copies), model_is_toy_fixture=True,
                  wall_time_seconds=time.time()-started, finished_at=datetime.now(timezone.utc).isoformat(),
                  cases=results, findings=findings)
    (BASE/'analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    lines = ['# Offline v6 external-evidence protocol result', '',
             'Ten fixed cases exercised the actual client main/play_one with a toy policy and offline native-rules server. '
             'No network, learned-weight update, training hand or performance-evaluation hand occurred. '
             'This is protocol evidence, not an independent rules-oracle or policy-strength test.', '',
             'Completed prefixes, counters/arithmetic, failure propagation/no retry, sampled decision replay, '
             'token redaction and source immutability passed. The following block future external qualification:', '']
    lines += [f'- {f["id"]}: {f["detail"]}' for f in findings]
    lines += ['', 'Production sources remain unchanged because the active curve owns its snapshot. '
              'Defer a separately registered repair and external-evidence/session-auditor validation until that run is terminal. '
              'No external admission is granted by the current audit.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    artifacts = [BASE/'analysis.json', BASE/'result_summary.md'] + sorted((BASE/'cases').rglob('*'))
    artifacts = [p for p in artifacts if p.is_file()]
    log(*[v for p in artifacts for v in ['--artifact', p]],
        '--metric', f'synthetic_cases={len(results)}', '--metric', f'source_pairs_verified={len(copies)}',
        '--note', 'Fixed offline protocol audit completed; all production sources unchanged. Missing attempt/partial journals and insufficient terminal/session validation block future external admission, not the current internal curve.')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name,
                    '--status', 'COMPLETED', '--summary', 'Ten fixed offline protocol cases completed with zero network; four external-evidence readiness gaps reproduced.',
                    '--conclusion', 'Completed-prefix and no-retry safety work, but current client evidence is insufficient for an external qualification run.',
                    '--decision', report['decision'], '--next-step', 'After the live curve relinquishes captured source ownership, register a journal/terminal/session evidence repair and validate it before external admission.',
                    '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0'], cwd=ROOT, check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
