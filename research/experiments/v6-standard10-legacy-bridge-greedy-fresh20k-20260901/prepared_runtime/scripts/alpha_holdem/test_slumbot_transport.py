"""Local protocol fixtures only: no Slumbot or environment poker games."""
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import threading

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT))
from alpha_holdem import play_slumbot as play
from alpha_holdem import slumbot_transport as transport
from scripts.alpha_holdem.test_slumbot_execution_telemetry import decision
from scripts.alpha_holdem.test_stochastic_slumbot_evidence import fixture, write_rows
from scripts.alpha_holdem import audit_slumbot_hand_evidence as evidence


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self.server.guard:
            self.server.connections += 1
            self.connection_id = self.server.connections

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.guard:
            self.server.calls.append(dict(path=self.path, payload=payload,
                cookie=self.headers.get('Cookie'), connection=self.connection_id))
        if self.path == '/drop':
            # Server has received the application POST; response delivery fails.
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        status = 503 if self.path == '/error' else 307 if self.path == '/redirect' else 200
        body = b'not-json' if self.path == '/badjson' else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Set-Cookie', 'fixture_cookie=must_not_carry')
        if status == 307:
            self.send_header('Location', '/unexpected-replay')
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


@pytest.fixture
def local_server():
    transport.close_transport()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.calls, server.connections, server.guard = [], 0, threading.Lock()
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}'
    finally:
        transport.close_transport()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def connection_reuse_probe(server, url, n=120):
    start = len(server.calls)
    control = []
    for i in range(n):
        with requests.post(url+'/echo', json={'index': i}, timeout=30) as response:
            response.raise_for_status()
            control.append(response.json())
    split = len(server.calls)
    pooled = [transport.post_json(url+'/echo', {'index': i}) for i in range(n)]
    old, new = server.calls[start:split], server.calls[split:]
    result = dict(control_requests=len(old), pooled_requests=len(new),
        control_connections=len({r['connection'] for r in old}),
        pooled_connections=len({r['connection'] for r in new}),
        identical_payloads_and_responses=control == pooled == [{'index': i} for i in range(n)],
        cross_request_cookies=sum(r['cookie'] is not None for r in old+new),
        actual_poker_hands=0, requests=n)
    assert result == dict(control_requests=n, pooled_requests=n,
        control_connections=n, pooled_connections=1, identical_payloads_and_responses=True,
        cross_request_cookies=0, actual_poker_hands=0, requests=n)
    return result


def test_real_http_connection_reuse(local_server):
    server, url = local_server
    connection_reuse_probe(server, url)


@pytest.mark.parametrize('path,error', [('/error', requests.HTTPError),
    ('/redirect', requests.HTTPError), ('/badjson', requests.JSONDecodeError),
    ('/drop', requests.ConnectionError)])
def test_error_never_replays_post_and_next_explicit_call_works(local_server, path, error):
    server, url = local_server
    with pytest.raises(error):
        transport.post_json(url+path, {'index': 1})
    assert len(server.calls) == 1 and server.calls[0]['path'] == path
    assert transport.post_json(url+'/echo', {'index': 2}) == {'index': 2}
    assert len(server.calls) == 2
    assert all(row['cookie'] is None for row in server.calls)


def test_connection_refused_is_not_retried(monkeypatch):
    import urllib3.util.connection
    transport.close_transport()
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise OSError('synthetic connection refused')
    monkeypatch.setattr(urllib3.util.connection, 'create_connection', fail)
    with pytest.raises(requests.ConnectionError):
        transport.post_json('http://127.0.0.1:1/never', {})
    assert len(calls) == 1
    transport.close_transport()


def test_pid_scoping_tls_and_retry_settings(monkeypatch):
    transport.close_transport()
    session = transport._get_session()
    assert session.verify is True and transport._get_session() is session
    for scheme in ('http://', 'https://'):
        adapter = session.get_adapter(scheme)
        assert adapter.max_retries.total == 0
        assert adapter._pool_maxsize == adapter._pool_connections == 1 and adapter._pool_block
    monkeypatch.setattr(transport, '_pid', -1)
    assert transport._get_session() is not session
    transport.close_transport()
    transport.close_transport()
    assert transport._session is None


def test_endpoint_payloads_unchanged(monkeypatch):
    calls = []
    def post(url, data):
        calls.append((url, data))
        return {'ok': True}
    monkeypatch.setattr(play, 'post_json', post)
    assert play.new_hand(None) == play.new_hand('private') == play.act('private', 'b200') == {'ok': True}
    assert calls == [('https://slumbot.com/slumbot/api/new_hand', {}),
        ('https://slumbot.com/slumbot/api/new_hand', {'token': 'private'}),
        ('https://slumbot.com/slumbot/api/act', {'token': 'private', 'incr': 'b200'})]


@pytest.mark.parametrize('kind', ['http', 'connection', 'out_of_turn'])
def test_strict_play_hand_never_fallbacks(monkeypatch, kind):
    initial = dict(token='private', action='' if kind == 'out_of_turn' else 'b200',
                   client_pos=0, hole_cards=['Ac', 'Ad'], board=[])
    monkeypatch.setattr(play, 'new_hand', lambda token: initial)
    monkeypatch.setattr(play, 'decide_action', decision)
    calls = []
    def fail(token, incr):
        calls.append(incr)
        raise (requests.HTTPError if kind == 'http' else requests.ConnectionError)('private')
    monkeypatch.setattr(play, 'act', fail)
    dump = io.StringIO()
    with pytest.raises((requests.RequestException, RuntimeError)):
        play.play_hand(None, None, 'cpu', policy_mode='sample', dump_fp=dump, strict_policy_execution=True)
    assert calls == ([] if kind == 'out_of_turn' else ['f'])
    assert dump.getvalue() == ''


@pytest.mark.parametrize('strict', [False, True])
def test_real_main_stops_or_legacy_skips_without_recount(monkeypatch, tmp_path, strict):
    # Production main executes once per process; this parametrized fixture does
    # not test PyTorch's one-shot inter-op initialization.
    monkeypatch.setattr(play.torch, 'set_num_interop_threads', lambda n: None)
    # Deterministically cover sub-clock-resolution mocked games in the summary.
    monkeypatch.setattr(play.time, 'time', lambda: 100.)
    calls, closed = [], []
    def hand(*args, **kwargs):
        assert kwargs['strict_policy_execution'] is strict
        calls.append(kwargs['hand_idx'])
        if len(calls) == 2:
            raise requests.ConnectionError('sensitive-token-must-not-escape')
        return 'private', 50
    monkeypatch.setattr(play, 'play_hand', hand)
    monkeypatch.setattr(play, 'close_transport', lambda: closed.append(True))
    raw, result, dump = [tmp_path/name for name in ['hands.jsonl', 'result.json', 'dump.jsonl']]
    argv = ['play_slumbot.py', '--strategy', 'fold', '--model', str(tmp_path/'no-model.pt'),
        '--hands', '3', '--policy-mode', 'sample', '--hand-results-jsonl', str(raw),
        '--dump-slumbot', str(dump), '--result-json', str(result)]
    if strict:
        argv.append('--strict-policy-execution')
    monkeypatch.setattr(sys, 'argv', argv)
    if strict:
        with pytest.raises(RuntimeError, match='Strict hand 2 failed') as exc:
            play.main()
        assert 'sensitive-token' not in str(exc.value) and not result.exists()
        assert calls == [0, 1]
        expected = [1]
    else:
        play.main()
        assert calls == [0, 1, 2] and json.loads(result.read_text())['successful_hands'] == 2
        expected = [1, 3]
    rows = evidence.jsonl(raw)
    assert [r['attempted_hand'] for r in rows] == expected
    assert [r['successful_hand'] for r in rows] == list(range(1, len(rows)+1))
    assert all(r['strict_policy_execution'] is strict and r['http_transport'] == transport.TRANSPORT_MODE for r in rows)
    assert closed == [True]
    # Windows rename verifies the raw file handle was released on failure too.
    raw.rename(tmp_path/'retained.jsonl')


def test_strict_and_legacy_clean_hand_have_identical_actions_and_evidence(monkeypatch):
    initial = dict(token='private', action='b200', client_pos=0,
        hole_cards=['Ac', 'Ad'], board=[])
    monkeypatch.setattr(play, 'new_hand', lambda token: initial)
    monkeypatch.setattr(play, 'decide_action', decision)
    outputs = []
    for strict in (False, True):
        calls = []
        def act(token, incr):
            calls.append(incr)
            return dict(initial, action='b200f', winnings=-100)
        monkeypatch.setattr(play, 'act', act)
        output = io.StringIO()
        result = play.play_hand(None, None, 'cpu', policy_mode='sample',
            dump_fp=output, strict_policy_execution=strict)
        outputs.append((result, calls, output.getvalue()))
    assert outputs[0] == outputs[1] and outputs[0][1] == ['f']


@pytest.mark.parametrize('damage', [None, 'raw_missing', 'raw_false', 'raw_mode', 'result_missing',
    'result_false', 'result_mode', 'manifest_null', 'manifest_false', 'manifest_mode'])
def test_strict_manifest_extension(tmp_path, damage):
    path, manifest = fixture(tmp_path)
    execution = dict(strict_policy_execution=True, http_transport=transport.TRANSPORT_MODE)
    manifest['execution'] = execution.copy()
    for i, spec in enumerate(manifest['sessions']):
        raw = evidence.jsonl(Path(spec['raw_hands']))
        result = json.loads(Path(spec['result']).read_text())
        for row in raw:
            row.update(execution)
        result.update(execution)
        if i == 0:
            if damage == 'raw_missing': raw[0].pop('strict_policy_execution')
            if damage == 'raw_false': raw[0]['strict_policy_execution'] = False
            if damage == 'raw_mode': raw[0]['http_transport'] = 'legacy'
            if damage == 'result_missing': result.pop('http_transport')
            if damage == 'result_false': result['strict_policy_execution'] = False
            if damage == 'result_mode': result['http_transport'] = 'legacy'
        write_rows(Path(spec['raw_hands']), raw)
        Path(spec['result']).write_text(json.dumps(result))
    if damage == 'manifest_null': manifest['execution'] = None
    if damage == 'manifest_false': manifest['execution']['strict_policy_execution'] = False
    if damage == 'manifest_mode': manifest['execution']['http_transport'] = 'legacy'
    path.write_text(json.dumps(manifest))
    if damage:
        with pytest.raises(ValueError):
            evidence.audit_manifest(path)
    else:
        assert evidence.audit_manifest(path)['execution_contract'] == execution
