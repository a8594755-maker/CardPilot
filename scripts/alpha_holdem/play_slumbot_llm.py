#!/usr/bin/env python3
"""
LLM vs Slumbot benchmark harness (DIAGNOSTIC evidence class).

Reuses the battle-tested Slumbot client from play_slumbot.py: parse_action,
compute_commitments, build_action_table (includes the per-street all-in cap
fix), new_hand/act. The LLM picks among the same 9-slot legal actions our
AlphaHoldem models see, via a strict JSON letter reply.

Anti-artifact rules (this harness exists to audit inflated LLM-vs-Slumbot
claims, so it must not have the classic score-inflating bugs):
- NO silent hand dropping. Transient API errors retry with backoff; if a hand
  still cannot be completed, the RUN ABORTS and reports hands completed so
  far. Every completed hand is counted exactly once.
- Every decision is logged to JSONL: hand idx, state, prompt, raw LLM reply,
  parsed action, fallback flag, latency. Fallback rate is reported; a
  benchmark with fallback rate > 2% is INVALID (the LLM wasn't really playing).
- Winnings come from Slumbot's own 'winnings' field in CHIPS. BB=100, so
  mean chips/hand numerically equals bb/100.

Usage:
  python scripts/alpha_holdem/play_slumbot_llm.py --backend deepseek \
      --model deepseek-v4-flash --hands 20 --out-prefix tmp/llm_ds_pilot --verbose
  python scripts/alpha_holdem/play_slumbot_llm.py --backend grok-cli \
      --hands 20 --out-prefix tmp/llm_grok_pilot
Env: DEEPSEEK_API_KEY for --backend deepseek.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from alpha_holdem.play_slumbot import (  # noqa: E402
    BIG_BLIND, STACK_SIZE, NUM_ACTIONS,
    parse_action, compute_commitments, build_action_table, new_hand, act,
)

STREET_NAMES = ['PREFLOP', 'FLOP', 'TURN', 'RIVER']
SLOT_DESCRIPTIONS = {
    0: 'FOLD',
    1: 'CHECK/CALL',
    8: 'ALL-IN',
}


# ═══════════════════════════════════════════════════════════
# Prompt construction
# ═══════════════════════════════════════════════════════════

def describe_history(state: dict) -> str:
    parts = []
    for st, actions in enumerate(state.get('street_actions', [])):
        if not actions:
            continue
        seat_desc = []
        for (kind, pos, amt) in actions:
            who = 'SB' if pos == 1 else 'BB'
            if kind == 'k':
                seat_desc.append(f'{who} checks')
            elif kind == 'c':
                seat_desc.append(f'{who} calls')
            elif kind == 'f':
                seat_desc.append(f'{who} folds')
            elif kind == 'b':
                seat_desc.append(f'{who} bets/raises to {amt} (this street)')
        parts.append(f'{STREET_NAMES[st]}: ' + '; '.join(seat_desc))
    return ' | '.join(parts) if parts else 'no actions yet (you are first to act)'


def build_prompt(hole_cards, board, state, client_pos, commitments, options):
    street = STREET_NAMES[min(state['st'], 3)]
    pos_desc = ('Small Blind / Button (you act FIRST preflop, LAST postflop)'
                if client_pos == 1 else 'Big Blind')
    board_desc = ' '.join(board) if board else 'none dealt yet'
    lines = [
        'You are an expert poker player in a HEADS-UP NO-LIMIT TEXAS HOLD\'EM cash game.',
        'Blinds 50/100 chips. Both players start each hand with 20000 chips (200 big blinds).',
        f'Your position: {pos_desc}.',
        f'Your hole cards: {" ".join(hole_cards)}.',
        f'Street: {street}. Board: {board_desc}.',
        f'Action history: {describe_history(state)}.',
        f'Pot: {commitments["pot"]} chips. To call: {commitments["to_call"]} chips. '
        f'Your remaining stack: {commitments["stack"]} chips.',
        'Legal actions:',
    ]
    for letter, slot, incr, desc in options:
        lines.append(f'  {letter}) {desc}')
    lines.append('Choose the single highest-EV action.')
    lines.append('Reply with ONLY this JSON on one line: {"action":"<LETTER>"}')
    return '\n'.join(lines)


def build_options(state: dict, commitments: dict):
    """Return [(letter, slot, incr, human description)] for legal slots."""
    mask, slot_to_incr = build_action_table(state)
    options = []
    letters = 'ABCDEFGHI'
    li = 0
    pot = max(commitments['pot'], 1)
    for slot in range(NUM_ACTIONS):
        if mask[slot] < 0.5 or slot_to_incr[slot] is None:
            continue
        incr = slot_to_incr[slot]
        if slot == 0:
            desc = 'FOLD'
        elif slot == 1:
            desc = (f'CALL {commitments["to_call"]} chips'
                    if commitments['to_call'] > 0 else 'CHECK')
        elif slot == 8:
            amt = int(incr[1:])
            desc = f'ALL-IN (raise to {amt} chips total this street)'
        else:
            amt = int(incr[1:])
            frac = (amt - state['street_last_bet_to']) / pot
            desc = f'RAISE to {amt} chips total this street (~{frac:.0%} of pot)'
        options.append((letters[li], slot, incr, desc))
        li += 1
    return options


# ═══════════════════════════════════════════════════════════
# LLM backends
# ═══════════════════════════════════════════════════════════

class DeepSeekBackend:
    def __init__(self, model: str):
        self.model = model
        self.key = os.environ.get('DEEPSEEK_API_KEY')
        if not self.key:
            raise SystemExit('DEEPSEEK_API_KEY not set')
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def ask(self, prompt: str) -> str:
        # v4-flash is a reasoning model: reasoning_content consumes the token
        # budget BEFORE content, so max_tokens must leave room for both.
        r = requests.post(
            'https://api.deepseek.com/chat/completions',
            headers={'Authorization': f'Bearer {self.key}'},
            json={
                'model': self.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.0,
                'max_tokens': 3000,
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        usage = data.get('usage', {})
        self.total_prompt_tokens += usage.get('prompt_tokens', 0)
        self.total_completion_tokens += usage.get('completion_tokens', 0)
        msg = data['choices'][0]['message']
        content = msg.get('content') or ''
        if not content.strip():
            # Reasoning exhausted the budget; salvage the choice from reasoning.
            content = msg.get('reasoning_content') or ''
        return content

    def usage_summary(self) -> str:
        return (f'prompt_tokens={self.total_prompt_tokens:,} '
                f'completion_tokens={self.total_completion_tokens:,}')


class GrokCliBackend:
    SCHEMA = ('{"type":"object","properties":{"action":{"type":"string",'
              '"enum":["A","B","C","D","E","F","G","H","I"]}},"required":["action"]}')
    SYSTEM = ('You are an expert poker decision engine. Evaluate the spot and answer '
              'with the requested JSON only. Never use tools.')

    def __init__(self, model: str | None):
        self.model = model or 'grok-build'
        self.exe = str(Path.home() / '.grok' / 'bin' / 'grok.exe')
        self.calls = 0

    def ask(self, prompt: str) -> str:
        cmd = [self.exe, '-p', prompt, '-m', self.model,
               '--output-format', 'json', '--json-schema', self.SCHEMA,
               '--no-subagents', '--disable-web-search', '--no-memory',
               '--verbatim', '--system-prompt-override', self.SYSTEM]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                             encoding='utf-8', errors='replace')
        if res.returncode != 0:
            raise RuntimeError(f'grok cli rc={res.returncode}: {res.stderr[:300]}')
        self.calls += 1
        out = res.stdout.strip()
        # Prefer the structured output from the JSON envelope.
        try:
            env = json.loads(out)
            so = env.get('structuredOutput') or {}
            if isinstance(so, dict) and so.get('action'):
                return json.dumps({'action': so['action']})
        except json.JSONDecodeError:
            pass
        return out

    def usage_summary(self) -> str:
        return f'cli_calls={self.calls:,} (token usage tracked by xAI account)'


# ═══════════════════════════════════════════════════════════
# Decision + hand loop
# ═══════════════════════════════════════════════════════════

def parse_reply(reply: str, options) -> tuple[int, str, bool]:
    """Return (slot, incr, used_fallback)."""
    valid = {letter: (slot, incr) for letter, slot, incr, _ in options}
    m = re.search(r'"action"\s*:\s*"([A-Ia-i])"', reply)
    if m and m.group(1).upper() in valid:
        slot, incr = valid[m.group(1).upper()]
        return slot, incr, False
    # Loose fallback: first standalone valid letter in the reply
    m2 = re.search(r'\b([A-Ia-i])\b', reply)
    if m2 and m2.group(1).upper() in valid:
        slot, incr = valid[m2.group(1).upper()]
        return slot, incr, False
    # Hard fallback: check/call
    for letter, slot, incr, _ in options:
        if slot == 1:
            return slot, incr, True
    letter, slot, incr, _ = options[0]
    return slot, incr, True


def llm_decide(backend, hole_cards, board, state, client_pos, log_fp, hand_idx,
               verbose=False, max_retries=3):
    commitments = compute_commitments(state)
    options = build_options(state, commitments)
    prompt = build_prompt(hole_cards, board, state, client_pos, commitments, options)

    last_err = None
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            reply = backend.ask(prompt)
            latency = time.time() - t0
            slot, incr, fallback = parse_reply(reply, options)
            log_fp.write(json.dumps({
                'hand': hand_idx, 'street': state['st'], 'pos': client_pos,
                'hole': hole_cards, 'board': board,
                'pot': commitments['pot'], 'to_call': commitments['to_call'],
                'options': [(l, i) for l, s, i, _ in options for i in [i]][:0] or
                           [[l, i] for l, s, i, _ in options],
                'reply': reply[:500], 'slot': slot, 'incr': incr,
                'fallback': fallback, 'latency_s': round(latency, 2),
            }) + '\n')
            log_fp.flush()
            if verbose:
                print(f'    [{STREET_NAMES[min(state["st"],3)]}] {hole_cards} '
                      f'board={board} -> "{reply[:60]}" -> {incr}'
                      f'{" (FALLBACK)" if fallback else ""}')
            return incr, fallback
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f'LLM backend failed after {max_retries} retries: {last_err}')


def play_hand_llm(backend, token, log_fp, hand_idx, verbose=False):
    r = new_hand(token)
    token = r.get('token', token)
    fallbacks = 0
    decisions = 0
    while True:
        action_str = r.get('action', '')
        client_pos = r.get('client_pos', 0)
        hole_cards = r.get('hole_cards', [])
        board = r.get('board', [])
        winnings = r.get('winnings')
        if winnings is not None:
            return token, winnings, decisions, fallbacks

        state = parse_action(action_str)
        if 'error' in state:
            raise RuntimeError(f'parse error on action string {action_str!r}')
        if state['pos'] != client_pos:
            raise RuntimeError(
                f'position desync: state.pos={state["pos"]} client_pos={client_pos} '
                f'action={action_str!r} — aborting instead of silently folding'
            )

        incr, fb = llm_decide(backend, hole_cards, board, state, client_pos,
                              log_fp, hand_idx, verbose=verbose)
        decisions += 1
        fallbacks += 1 if fb else 0
        r = act(token, incr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', choices=('deepseek', 'grok-cli'), required=True)
    ap.add_argument('--model', default=None,
                    help='deepseek-v4-flash / deepseek-v4-pro for deepseek; '
                         'model id for grok-cli (default: CLI default)')
    ap.add_argument('--hands', type=int, default=20)
    ap.add_argument('--out-prefix', default='tmp/llm_slumbot')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    if args.backend == 'deepseek':
        backend = DeepSeekBackend(args.model or 'deepseek-v4-flash')
    else:
        backend = GrokCliBackend(args.model)

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(f'{out_prefix}_decisions.jsonl')
    summary_path = Path(f'{out_prefix}_summary.json')

    token = None
    winnings_per_hand = []
    total_decisions = 0
    total_fallbacks = 0
    t_start = time.time()

    with open(log_path, 'w', encoding='utf-8') as log_fp:
        for h in range(args.hands):
            try:
                token, w, d, fb = play_hand_llm(backend, token, log_fp, h,
                                                verbose=args.verbose)
            except Exception as e:  # noqa: BLE001
                print(f'ABORT at hand {h}: {e}')
                print('No silent skipping — reporting completed hands only.')
                break
            winnings_per_hand.append(w)
            total_decisions += d
            total_fallbacks += fb
            if args.verbose or (h + 1) % 25 == 0:
                n = len(winnings_per_hand)
                mean = sum(winnings_per_hand) / n
                print(f'[{n}/{args.hands}] hand winnings={w:+d} chips | '
                      f'running mean={mean:+.1f} chips/hand (= bb/100) | '
                      f'fallbacks={total_fallbacks}/{total_decisions}')

    n = len(winnings_per_hand)
    if n == 0:
        raise SystemExit('no completed hands')
    mean = sum(winnings_per_hand) / n
    var = sum((w - mean) ** 2 for w in winnings_per_hand) / max(n - 1, 1)
    sd = math.sqrt(var)
    ci = 1.96 * sd / math.sqrt(n)
    elapsed = time.time() - t_start
    fallback_rate = total_fallbacks / max(total_decisions, 1)

    summary = {
        'backend': args.backend,
        'model': args.model,
        'hands': n,
        'bb_per_100': round(mean, 2),          # chips/hand == bb/100 at BB=100
        'ci95_bb_per_100': round(ci, 2),
        'sd_chips_per_hand': round(sd, 1),
        'decisions': total_decisions,
        'fallbacks': total_fallbacks,
        'fallback_rate': round(fallback_rate, 4),
        'valid': fallback_rate <= 0.02,
        'elapsed_s': round(elapsed, 1),
        'sec_per_hand': round(elapsed / n, 2),
        'usage': backend.usage_summary(),
        'evidence_class': 'llm_diagnostic',
        'decisions_log': str(log_path),
    }
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    if fallback_rate > 0.02:
        print('WARNING: fallback rate > 2% — benchmark INVALID '
              '(the LLM was not really choosing actions).')


if __name__ == '__main__':
    main()
