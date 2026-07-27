#!/usr/bin/env python3
"""
Batched LLM vs Slumbot benchmark (DIAGNOSTIC) — "一車一車" mode.

Poker decisions are sequential WITHIN a hand but independent ACROSS tables, so
T table-threads play concurrent Slumbot sessions and submit pending decisions
to a shared queue; B batcher-threads pack up to K spots into ONE LLM call
(json-schema-forced {"answers":[{"id":N,"action":"<letter>"}]}) and fan the
answers back out. Measured on grok-build: K=20 costs the same latency as K=6,
so throughput per server slot is ~7x the single-spot harness.

Same anti-artifact rules as play_slumbot_llm.py:
- every completed hand counted exactly once; a table that desyncs/aborts is
  recorded (not silently dropped) and its completed hands still count
- per-decision JSONL: spot text hash, raw answer, fallback flag, batch id
- missing/unparseable answer for a spot => fallback (check/call) + flagged;
  fallback rate > 2% invalidates the benchmark
- winnings come from Slumbot's own 'winnings' field (chips; == bb/100 at BB=100)

Early stop: create <out_dir>/STOP to finish current hands and exit; interim
summaries are written every ~60s to <out_dir>/interim_summary.json.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from alpha_holdem.play_slumbot import (  # noqa: E402
    parse_action, compute_commitments, build_action_table, new_hand, act,
)
from alpha_holdem.play_slumbot_llm import (  # noqa: E402
    build_options, build_prompt, STREET_NAMES,
)

GROK_EXE = str(Path.home() / '.grok' / 'bin' / 'grok.exe')
BATCH_SCHEMA = json.dumps({
    'type': 'object',
    'properties': {'answers': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'integer'},
                       'action': {'type': 'string',
                                  'enum': list('ABCDEFGHI')}},
        'required': ['id', 'action']}}},
    'required': ['answers'],
})
SYSTEM = ('You are an expert poker decision engine answering multiple INDEPENDENT '
          'heads-up NLHE spots from different tables. Evaluate each spot on its own. '
          'Answer with the requested JSON only. Never use tools.')


class Spot:
    __slots__ = ('text', 'letters', 'event', 'answer', 'fallback', 'table', 'street')

    def __init__(self, text, letters, table, street):
        self.text = text
        self.letters = letters      # set of valid letters for this spot
        self.event = threading.Event()
        self.answer = None          # letter or None
        self.fallback = False
        self.table = table
        self.street = street


class Bench:
    def __init__(self, args):
        self.args = args
        self.queue = deque()
        self.qlock = threading.Condition()
        self.stop = threading.Event()
        self.winnings = []          # per completed hand (chips)
        self.stats_lock = threading.Lock()
        self.decisions = 0
        self.fallbacks = 0
        self.batches = 0
        self.batch_lat = []
        self.tables_aborted = 0
        self.hands_done = 0
        self.out_dir = Path(args.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_fp = open(self.out_dir / 'decisions.jsonl', 'w', encoding='utf-8')
        self.log_lock = threading.Lock()
        self.t0 = time.time()

    # ---------- batching ----------

    def submit(self, spot: Spot):
        with self.qlock:
            self.queue.append(spot)
            self.qlock.notify()

    def take_batch(self, k: int, window_s: float):
        deadline = time.time() + window_s
        batch = []
        with self.qlock:
            while len(batch) < k and not self.stop.is_set():
                while self.queue and len(batch) < k:
                    batch.append(self.queue.popleft())
                if len(batch) >= k:
                    break
                remaining = deadline - time.time()
                if remaining <= 0 and batch:
                    break
                self.qlock.wait(timeout=max(remaining, 0.05) if batch else 0.5)
        return batch

    def call_llm(self, prompt: str) -> dict | None:
        cmd = [GROK_EXE, '-p', prompt, '-m', self.args.model,
               '--output-format', 'json', '--json-schema', BATCH_SCHEMA,
               '--no-subagents', '--disable-web-search', '--no-memory',
               '--verbatim', '--system-prompt-override', SYSTEM]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=420,
                             encoding='utf-8', errors='replace')
        if res.returncode != 0:
            return None
        try:
            env = json.loads(res.stdout.strip())
            return env.get('structuredOutput') or None
        except json.JSONDecodeError:
            return None

    def batcher(self):
        while not self.stop.is_set():
            batch = self.take_batch(self.args.batch_size, self.args.batch_window_s)
            if not batch:
                continue
            header = (f'Answer {len(batch)} INDEPENDENT poker spots '
                      f'(different tables, unrelated hands).\n\n')
            body = []
            for i, spot in enumerate(batch, start=1):
                body.append(f'=== SPOT {i} ===\n{spot.text}')
            footer = ('\n\nReply with ONLY JSON: {"answers":[{"id":1,"action":"<LETTER>"},...]} '
                      f'covering ALL ids 1..{len(batch)} exactly once.')
            prompt = header + '\n\n'.join(body) + footer

            answers = None
            t0 = time.time()
            for attempt in range(2):
                so = None
                try:
                    so = self.call_llm(prompt)
                except Exception:
                    so = None
                if so and isinstance(so.get('answers'), list):
                    answers = {a.get('id'): str(a.get('action', '')).upper()
                               for a in so['answers'] if isinstance(a, dict)}
                    break
                time.sleep(1.5)
            lat = time.time() - t0

            with self.stats_lock:
                self.batches += 1
                self.batch_lat.append(lat)

            for i, spot in enumerate(batch, start=1):
                letter = (answers or {}).get(i)
                if letter in spot.letters:
                    spot.answer = letter
                else:
                    spot.answer = None
                    spot.fallback = True
                spot.event.set()

    # ---------- tables ----------

    def play_table(self, tid: int, hands_target: int):
        token = None
        done_here = 0
        try:
            while done_here < hands_target and not self.stop.is_set():
                if (self.out_dir / 'STOP').exists():
                    self.stop.set()
                    break
                token, w = self.play_one_hand(token, tid)
                done_here += 1
                with self.stats_lock:
                    self.winnings.append(w)
                    self.hands_done += 1
        except Exception as e:  # noqa: BLE001
            with self.stats_lock:
                self.tables_aborted += 1
            with self.log_lock:
                self.log_fp.write(json.dumps({
                    'table': tid, 'event': 'table_abort', 'error': str(e)[:300],
                    'completed_hands': done_here}) + '\n')

    def play_one_hand(self, token, tid):
        r = new_hand(token)
        token = r.get('token', token)
        while True:
            action_str = r.get('action', '')
            client_pos = r.get('client_pos', 0)
            hole_cards = r.get('hole_cards', [])
            board = r.get('board', [])
            winnings = r.get('winnings')
            if winnings is not None:
                return token, winnings

            state = parse_action(action_str)
            if 'error' in state:
                raise RuntimeError(f'parse error: {action_str!r}')
            if state['pos'] != client_pos:
                raise RuntimeError(f'position desync at {action_str!r}')

            commitments = compute_commitments(state)
            options = build_options(state, commitments)
            text = build_prompt(hole_cards, board, state, client_pos,
                                commitments, options)
            # Strip the single-spot reply instruction; the batcher adds its own.
            text = text.rsplit('Reply with ONLY', 1)[0].rstrip()
            letters = {letter for letter, _, _, _ in options}
            spot = Spot(text, letters, tid, state['st'])
            self.submit(spot)
            got = spot.event.wait(timeout=600)

            incr = None
            fallback = spot.fallback or not got
            if not fallback and spot.answer:
                for letter, slot, inc, _ in options:
                    if letter == spot.answer:
                        incr = inc
                        break
            if incr is None:
                fallback = True
                for letter, slot, inc, _ in options:
                    if slot == 1:
                        incr = inc
                        break
                incr = incr or options[0][2]

            with self.stats_lock:
                self.decisions += 1
                self.fallbacks += 1 if fallback else 0
            with self.log_lock:
                self.log_fp.write(json.dumps({
                    'table': tid, 'street': state['st'], 'hole': hole_cards,
                    'board': board, 'answer': spot.answer, 'incr': incr,
                    'fallback': fallback}) + '\n')

            r = act(token, incr)

    # ---------- reporting ----------

    def summary(self, final: bool):
        with self.stats_lock:
            w = list(self.winnings)
            decisions, fallbacks = self.decisions, self.fallbacks
            batches = self.batches
            lat = sorted(self.batch_lat)
            aborted = self.tables_aborted
        n = len(w)
        mean = sum(w) / n if n else 0.0
        var = sum((x - mean) ** 2 for x in w) / max(n - 1, 1) if n > 1 else 0.0
        sd = math.sqrt(var)
        ci = 1.96 * sd / math.sqrt(n) if n else 0.0
        frate = fallbacks / max(decisions, 1)
        return {
            'final': final,
            'backend': 'grok-cli-batched',
            'model': self.args.model,
            'hands': n,
            'bb_per_100': round(mean, 2),
            'ci95_bb_per_100': round(ci, 2),
            'sd_chips_per_hand': round(sd, 1),
            'decisions': decisions,
            'fallbacks': fallbacks,
            'fallback_rate': round(frate, 4),
            'valid': frate <= 0.02,
            'batches': batches,
            'batch_lat_p50': round(lat[len(lat) // 2], 1) if lat else None,
            'tables_aborted': aborted,
            'elapsed_s': round(time.time() - self.t0, 0),
            'hands_per_hour': round(n / max(time.time() - self.t0, 1) * 3600, 0),
            'evidence_class': 'llm_diagnostic',
        }

    def monitor(self):
        while not self.stop.is_set():
            time.sleep(60)
            s = self.summary(final=False)
            (self.out_dir / 'interim_summary.json').write_text(json.dumps(s, indent=2))
            print(f"[interim] hands={s['hands']} bb/100={s['bb_per_100']:+.1f} "
                  f"±{s['ci95_bb_per_100']:.1f} fallback={s['fallback_rate']:.1%} "
                  f"h/hr={s['hands_per_hour']:.0f} batches={s['batches']} "
                  f"lat_p50={s['batch_lat_p50']}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='grok-build')
    ap.add_argument('--total-hands', type=int, required=True)
    ap.add_argument('--tables', type=int, default=500)
    ap.add_argument('--batchers', type=int, default=25)
    ap.add_argument('--batch-size', type=int, default=20)
    ap.add_argument('--batch-window-s', type=float, default=1.5)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()

    bench = Bench(args)
    per_table = max(1, args.total_hands // args.tables)

    threads = []
    for b in range(args.batchers):
        t = threading.Thread(target=bench.batcher, daemon=True)
        t.start()
        threads.append(t)
    mon = threading.Thread(target=bench.monitor, daemon=True)
    mon.start()

    table_threads = []
    for tid in range(args.tables):
        t = threading.Thread(target=bench.play_table, args=(tid, per_table), daemon=True)
        t.start()
        table_threads.append(t)
        time.sleep(0.02)

    for t in table_threads:
        t.join()
    bench.stop.set()
    with bench.qlock:
        bench.qlock.notify_all()

    s = bench.summary(final=True)
    (bench.out_dir / 'merged_summary.json').write_text(json.dumps(s, indent=2))
    bench.log_fp.close()
    print(json.dumps(s, indent=2))
    if s['fallback_rate'] > 0.02:
        print('WARNING: fallback rate > 2% — benchmark INVALID.')


if __name__ == '__main__':
    main()
