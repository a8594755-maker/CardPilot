"""Single-process HTTP connection reuse without replaying state-changing POSTs.

One synchronous poker client owns this transport. No application-level retry,
redirect replay, cross-request cookies, or change to Requests' TLS verification.
"""
import atexit
import os
import threading

import requests
from requests.adapters import HTTPAdapter

TRANSPORT_MODE = 'persistent_session_no_retries_v1'
_session = None
_pid = None
_lock = threading.Lock()


def _close_unlocked():
    global _session, _pid
    if _session is not None:
        _session.close()
    _session, _pid = None, None


def close_transport():
    """Idempotently release this process' pooled sockets, including on exit."""
    with _lock:
        _close_unlocked()


def _get_session():
    global _session, _pid
    if _session is None or _pid != os.getpid():
        _close_unlocked()
        _session = requests.Session()
        for scheme in ('http://', 'https://'):
            _session.mount(scheme, HTTPAdapter(
                pool_connections=1, pool_maxsize=1, pool_block=True, max_retries=0))
        _pid = os.getpid()
    return _session


def post_json(url, payload):
    """Send exactly one POST; consume/close responses so connections are reusable.

    Any error propagates. In particular, never retry an ambiguous read failure:
    the server may already have dealt a hand or applied the requested action.
    """
    with _lock:
        session = _get_session()
        # The old per-call requests.post did not retain cookies across calls.
        session.cookies.clear()
        response = None
        try:
            response = session.post(url, json=payload, timeout=30, allow_redirects=False)
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise requests.HTTPError('API redirect refused; no POST replay', response=response)
            return response.json()
        finally:
            if response is not None:
                response.close()
            session.cookies.clear()


def _after_fork():
    # A parent's thread could have held the lock at fork. The PID guard will
    # replace inherited sockets before use; Windows spawn starts fresh already.
    global _lock
    _lock = threading.Lock()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork)
atexit.register(close_transport)
