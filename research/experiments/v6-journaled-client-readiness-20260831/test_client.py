"""Preserved offline client/session failure fixtures. No real poker requests."""
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(BASE))
from alpha_holdem import play_slumbot_v6_journaled as client
from alpha_holdem import audit_slumbot_v6_session as audit
from alpha_holdem.slumbot_journal_v6 import canonical, digest, Journal
from alpha_holdem.execution_v6 import sha256_file, load_policy
from offline_fixture import ToyPolicy, Server


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        cls.output = Path(os.environ['JOURNAL_TEST_OUTPUT'])
        cls.output.mkdir(exist_ok=False)
        cls.connections = []
        def deny(*a, **kw):
            cls.connections.append('connection')
            raise AssertionError('External network forbidden')
        cls.guards = [patch.object(socket.socket, 'connect', deny), patch.object(socket, 'create_connection', deny)]
        for guard in cls.guards: guard.start()

    @classmethod
    def tearDownClass(cls):
        for guard in reversed(cls.guards): guard.stop()
        (cls.output/'network_guard.json').write_text(json.dumps(dict(connections=cls.connections))+'\n')
        assert not cls.connections

    def setUp(self):
        self.directory = self.output/self._testMethodName
        self.directory.mkdir()
        self.model_path = self.directory/'toy_model.txt'
        self.model_path.write_text('EXPLICIT_OFFLINE_TOY_POLICY_NOT_A_CHECKPOINT\n')
        self.model = ToyPolicy().eval()
        self.model_hash = sha256_file(self.model_path)

    def run_case(self, case='normal', *, label=None, seed=1001, session_id=None, prefix=None,
                 callback=None, expected_failure=False, model=None, model_path=None, model_hash=None):
        label = label or case
        directory = self.directory/label
        directory.mkdir()
        server = Server(case, prefix or label, callback)
        out = directory/'client'
        exception = None
        try:
            client.run_session(model or self.model, model_path or self.model_path, model_hash or self.model_hash,
                hands=2, seed=seed, session_id=session_id or label, out_dir=out,
                new_hand_fn=server.new_hand, act_fn=server.act,
                command=['offline_fixture', case, str(seed), session_id or label])
        except RuntimeError as exc:
            exception = str(exc)
        finally:
            (directory/'fixture.json').write_text(json.dumps(dict(case=case, calls=server.calls,
                completed_fixture_trajectories=server.completed, hand_attempts=server.hand,
                exception=exception), indent=2)+'\n')
        self.assertEqual(exception is not None, expected_failure)
        for path in out.iterdir():
            if path.is_file(): self.assertNotIn('OFFLINE_ONLY_', path.read_text())
        result = audit.audit_session(out, model=model or self.model, expected_model_sha256=model_hash or self.model_hash)
        (directory/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
        self.assertEqual(result['status'], 'INCOMPLETE' if expected_failure else 'PASS')
        return out, result, server

    def test_normal_rotation_omission_and_allin(self):
        for case in ['normal', 'opponent_fold', 'midhand_rotation', 'interhand_rotation', 'omitted_unchanged_token', 'allin_suffix']:
            with self.subTest(case=case):
                _, result, server = self.run_case(case)
                self.assertEqual(result['successful_hands'], 2)
                self.assertEqual(server.hand, 2)
                if case in ['midhand_rotation', 'interhand_rotation']: self.assertGreater(len(result['token_sha256']), 1)
                if case == 'opponent_fold': self.assertEqual(result['decision_replays'], 0)

    def test_ambiguous_first_second_requests_no_retry(self):
        for case in ['new_hand_first_error', 'new_hand_second_error', 'act_first_error', 'act_second_error']:
            with self.subTest(case=case):
                out, result, server = self.run_case(case, expected_failure=True)
                expected = 1 if 'second' in case else 0
                self.assertEqual(result['successful_hands'], expected)
                self.assertEqual(server.hand, expected+1)
                self.assertIsNotNone(result['pending_request_id'])
                self.assertEqual(result['protocol_failures'][-1]['kind'], 'request_error')
                intents = [e for e in audit.read_lines(out/'journal.jsonl')[0] if e['event'] == 'request_intent']
                self.assertEqual(len(intents), len(server.calls))
                if case.startswith('act'):
                    self.assertEqual(sum(c['method'] == 'act' and c['hand'] == expected+1 for c in server.calls), 1)
                    self.assertIsNotNone(intents[-1]['decision'])

    def test_invalid_public_responses_are_preserved(self):
        for case in ['missing_initial_token', 'invalid_token', 'noninteger_reward', 'out_of_bounds',
                     'nonfinite_reward', 'premature_terminal', 'missing_showdown_cards', 'wrong_server_count',
                     'wrong_server_total', 'missing_server_count', 'server_error', 'missing_board',
                     'changed_cards', 'changed_seat', 'changed_history', 'nested_token']:
            with self.subTest(case=case):
                _, result, server = self.run_case(case, expected_failure=True)
                self.assertEqual(result['successful_hands'], 0)
                self.assertEqual(server.hand, 1)
                self.assertEqual(result['protocol_failures'][-1]['kind'], 'invalid_response')

    def test_policy_failure_preserves_received_prefix(self):
        with patch.object(client, 'external_decision', side_effect=ValueError('OFFLINE_ONLY_secret')):
            out, result, server = self.run_case(expected_failure=True)
        self.assertEqual(len(server.calls), 1)
        summary = json.loads((out/'summary.json').read_text())
        self.assertEqual(summary['phase'], 'policy_decision')
        self.assertEqual(result['successful_hands'], 0)

    def test_frozen_checkpoint_changed_no_qualification(self):
        def alter_fixture_only(): self.model_path.write_text('DIFFERENT_OFFLINE_FIXTURE\n')
        out, result, _ = self.run_case(callback=alter_fixture_only, expected_failure=True)
        self.assertEqual(result['successful_hands'], 2)
        self.assertFalse(json.loads((out/'summary.json').read_text())['frozen_identity_verified'])

    def test_frozen_runtime_changed_no_qualification(self):
        fake_runtime = self.directory/'fake_runtime.txt'
        fake_runtime.write_text('original')
        fake_hash = sha256_file(fake_runtime)
        with patch.object(client, 'runtime_hashes', return_value={str(fake_runtime):fake_hash}):
            out, result, _ = self.run_case(callback=lambda: fake_runtime.write_text('changed'), expected_failure=True)
        self.assertEqual(result['successful_hands'], 2)
        self.assertFalse(json.loads((out/'summary.json').read_text())['frozen_identity_verified'])

    def test_persistence_failure_before_request(self):
        original = Journal.append
        def fail(journal, event, **fields):
            if event == 'request_intent': raise OSError('fixture disk failure')
            return original(journal, event, **fields)
        with patch.object(Journal, 'append', fail):
            _, result, server = self.run_case(expected_failure=True)
        self.assertEqual(len(server.calls), 0)
        self.assertEqual(result['request_count'], 0)

    def test_response_persistence_failure_keeps_ambiguous_intent(self):
        original = Journal.append
        def fail(journal, event, **fields):
            if event == 'request_response': raise OSError('fixture disk failure')
            return original(journal, event, **fields)
        with patch.object(Journal, 'append', fail):
            _, result, server = self.run_case(expected_failure=True)
        self.assertEqual(len(server.calls), 1)
        self.assertEqual(result['pending_request_id'], 1)

    def test_partial_raw_write_never_counts_as_completed(self):
        original = client.append_line
        def fail(handle, row):
            if Path(handle.name).name == 'hands.jsonl':
                handle.write(canonical(row)[:30])
                handle.flush()
                os.fsync(handle.fileno())
                raise OSError('fixture partial hand write')
            return original(handle, row)
        with patch.object(client, 'append_line', fail):
            _, result, _ = self.run_case(expected_failure=True)
        self.assertEqual(result['successful_hands'], 0)
        self.assertEqual(result['committed_without_raw'], 1)
        self.assertTrue(result['partial_hands'])

    def test_abrupt_exit_after_fsynced_intent(self):
        out = self.directory/'child_client'
        command = [sys.executable, str(BASE/'crash_after_intent.py'), str(self.model_path), str(out)]
        with (self.directory/'child_stdout.log').open('x') as handle:
            proc = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, cwd=ROOT)
            code = proc.wait(timeout=60)
        (self.directory/'process.json').write_text(json.dumps(dict(command=command, pid=proc.pid, exit_code=code))+'\n')
        self.assertEqual(code, 17)
        result = audit.audit_session(out, model=self.model, expected_model_sha256=self.model_hash)
        (self.directory/'audit.json').write_text(json.dumps(result)+'\n')
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['pending_request_id'], 1)
        self.assertFalse((out/'summary.json').exists())

    def test_no_overwrite_and_bad_configuration(self):
        out, _, _ = self.run_case()
        before = sha256_file(out/'journal.jsonl')
        with self.assertRaises(FileExistsError):
            client.run_session(self.model, self.model_path, self.model_hash, hands=2, seed=1, session_id='other', out_dir=out)
        self.assertEqual(before, sha256_file(out/'journal.jsonl'))
        for hands, seed, sid in [(0, 1, 'bad'), (-1, 1, 'bad'), (2, True, 'bad'), (2, 1, '../bad')]:
            with self.assertRaises(ValueError):
                client.run_session(self.model, self.model_path, self.model_hash, hands=hands, seed=seed, session_id=sid, out_dir=self.directory/'bad')

    def tamper(self, original, label, change, *, rehash=False):
        out = self.directory/label
        shutil.copytree(original, out)
        events, _ = audit.read_lines(out/'journal.jsonl')
        rows, _ = audit.read_lines(out/'hands.jsonl')
        summary = json.loads((out/'summary.json').read_text())
        change(events, rows, summary)
        if rehash:
            head = '0'*64
            for index, event in enumerate(events, 1):
                event.update(sequence=index, previous_sha256=head)
                event.pop('event_sha256')
                event['event_sha256'] = digest(event)
                head = event['event_sha256']
            summary['journal_final_sha256'] = head
        (out/'journal.jsonl').write_bytes(b''.join(canonical(e)+b'\n' for e in events))
        (out/'hands.jsonl').write_bytes(b''.join(canonical(e)+b'\n' for e in rows))
        summary.update(journal_sha256=sha256_file(out/'journal.jsonl'), hands_sha256=sha256_file(out/'hands.jsonl'))
        (out/'summary.json').write_bytes(canonical(summary)+b'\n')
        return out

    def test_raw_summary_and_hash_tampering(self):
        original, _, _ = self.run_case()
        def bad_raw(e, rows, s): rows[0]['winnings_chips'] += 1
        def bad_summary(e, rows, s): s['cumulative_chips'] += 1
        def bad_event(e, rows, s): e[1]['hand'] = 2
        for label, change in [('raw', bad_raw), ('summary', bad_summary), ('journal', bad_event)]:
            out = self.tamper(original, label, change)
            with self.subTest(label=label), self.assertRaises(ValueError): audit.audit_session(out, model=self.model)

    def test_semantic_token_and_seed_tampering_after_rehash(self):
        original, _, _ = self.run_case()
        def wrong_token(events, rows, summary):
            next(e for e in events if e['event'] == 'request_intent')['token_in_sha256'] = '1'*64
        def wrong_seed(events, rows, summary):
            events[0]['policy_seed'] += 1
            summary['policy_seed'] += 1
        for label, change, message in [('token', wrong_token, 'token'), ('seed', wrong_seed, 'RNG')]:
            out = self.tamper(original, label, change, rehash=True)
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message): audit.audit_session(out, model=self.model)

    def test_model_replay_detects_forged_valid_distribution(self):
        original, _, _ = self.run_case()
        def change(events, rows, summary):
            decision = next(e['decision'] for e in events if e['event'] == 'request_intent' and e['method'] == 'act')
            decision['behavior_probs'][0:2] = [.1, .9]
            decision['behavior_action_probability'] = .9
        out = self.tamper(original, 'probability', change, rehash=True)
        with self.assertRaisesRegex(ValueError, 'model decision replay'): audit.audit_session(out, model=self.model)

    def test_multiple_independent_streams_and_collisions(self):
        a, _, _ = self.run_case(label='session_a', seed=1001)
        b, _, _ = self.run_case(label='session_b', seed=1002)
        good = audit.audit_sessions([a, b], model=self.model, expected_model_sha256=self.model_hash)
        self.assertEqual(good['successful_hands'], 4)
        self.assertFalse(good['server_rng_independence_proven'])
        (self.directory/'multi_session_audit.json').write_text(json.dumps(good, indent=2)+'\n')
        for label, kwargs in [('same_id', dict(session_id='session_a', seed=1003)),
                              ('same_seed', dict(seed=1001)),
                              ('same_token', dict(seed=1004, prefix='session_a'))]:
            c, _, _ = self.run_case(label=label, **kwargs)
            with self.subTest(label=label), self.assertRaises(ValueError): audit.audit_sessions([a, c], model=self.model)
        with self.assertRaises(ValueError): audit.audit_sessions([a, a], model=self.model)

    def test_actual_main_entrypoint(self):
        server = Server(prefix='main_fixture')
        out = self.directory/'cli'
        command = ['play_slumbot_v6_journaled.py', '--model', str(self.model_path), '--hands', '2',
                   '--seed', '1001', '--session-id', 'main_fixture', '--out-dir', str(out)]
        captured = io.StringIO()
        with patch.object(client, 'load_policy', return_value=(self.model, {}, self.model_hash)), \
             patch.object(client, 'new_hand', server.new_hand), patch.object(client, 'act', server.act), \
             patch.object(torch, 'set_num_threads'), patch.object(torch, 'set_num_interop_threads'), \
             patch.object(sys, 'argv', command), redirect_stdout(captured): client.main()
        (self.directory/'stdout.log').write_text(captured.getvalue())
        self.assertNotIn('OFFLINE_ONLY_', captured.getvalue())
        self.assertEqual(audit.audit_session(out, model=self.model)['status'], 'PASS')
        (self.directory/'fixture.json').write_text(json.dumps(dict(calls=server.calls, completed_fixture_trajectories=server.completed))+'\n')

    def test_real_frozen_policy_shared_inference_replay(self):
        path = ROOT/'research/experiments/v6-source-kl-retention-pilot-20260831/frozen/anchor0.pt'
        expected = '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
        self.assertEqual(sha256_file(path), expected)
        model, _, model_hash = load_policy(path, 'cpu')
        _, result, _ = self.run_case(label='real_source_execution_fixture', seed=20260923,
                                    model=model, model_path=path, model_hash=model_hash)
        self.assertGreater(result['decision_replays'], 0)
        self.assertEqual(sha256_file(path), expected)


if __name__ == '__main__': unittest.main()
