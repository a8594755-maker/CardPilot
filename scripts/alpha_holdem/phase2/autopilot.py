"""Phase 2 Autopilot Orchestrator.

State-machine runner for the CardPilot poker-AI training pipeline. Reads
`autopilot_config.yaml`, persists progress in `autopilot_state.json`, and
emits a markdown report per run under `autopilot_runs/{run_id}/`.

Commands:
  status                Show current stage and recent history.
  next                  Compute the next decision (CONTINUE/ASK_USER/STOP/ERROR)
                        without executing anything.
  run-once [--dry-run]  Execute (or simulate) the current stage and advance.
  run-until-stop        Loop run-once until ASK_USER / STOP / ERROR.
  explain               Dump project/budgets/stages overview.
  reset-state --confirm Reset state to bootstrap.
  approve-runway --confirm [--hours N]
                        Activate the pre-approved runway. Required before any
                        stage with `requires_runway: true` may run.

Decision semantics:
  CONTINUE   Stage is autonomous-safe (diagnostic/smoke/eval inside budget).
  ASK_USER   Stage requires explicit user approval (decision_only or budget).
  STOP       A hard-stop gate triggered on the most recent run.
  ERROR      Subprocess failed, timed out, or config/state is malformed.

This module does no ML on its own — it only orchestrates calls to existing
Phase 2 scripts.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print('ERROR: PyYAML required. Install with: pip install pyyaml', file=sys.stderr)
    sys.exit(2)


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
CONFIG_PATH = THIS_DIR / 'autopilot_config.yaml'
STATE_PATH = THIS_DIR / 'autopilot_state.json'
RUNS_DIR = THIS_DIR / 'autopilot_runs'

GATE_OP_SUFFIXES = ['_lte', '_gte', '_lt', '_gt', '_eq']
_MISSING = object()  # sentinel: distinguishes "key absent" from "key present with null"


class Decision(str, Enum):
    CONTINUE = 'CONTINUE'
    ASK_USER = 'ASK_USER'
    STOP = 'STOP'
    ERROR = 'ERROR'


@dataclass
class StageResult:
    stage_id: str
    decision: Decision
    reason: str
    command: str | None = None
    runtime_s: float | None = None
    pass_gates: list[dict] = field(default_factory=list)
    fail_gates: list[dict] = field(default_factory=list)
    hard_stops_triggered: list[dict] = field(default_factory=list)
    next_stage: str | None = None
    run_id: str | None = None


# ----------------------------------------------------------------------------
# Config / state IO

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f'Missing config: {CONFIG_PATH}')
    return yaml.safe_load(CONFIG_PATH.read_text(encoding='utf-8'))


def load_state() -> dict:
    if not STATE_PATH.exists():
        return new_state()
    return json.loads(STATE_PATH.read_text(encoding='utf-8'))


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def new_state() -> dict:
    return {
        'current_stage_id': 'bootstrap',
        'history': [],
        'runway': {
            'active': False,
            'approved_at': None,
            'approved_until': None,
            'experiments_used': 0,
        },
        'created_at': _now_iso(),
        'schema_version': 1,
    }


def _now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def find_stage(config: dict, sid: str) -> dict | None:
    for s in config.get('stages', []):
        if s.get('id') == sid:
            return s
    return None


# ----------------------------------------------------------------------------
# Gate evaluation

def _split_gate_key(key: str) -> tuple[str, str] | None:
    """`final_value_loss_lt` -> ('final_value_loss', 'lt'). None if no suffix."""
    for suf in GATE_OP_SUFFIXES:
        if key.endswith(suf):
            return key[: -len(suf)], suf[1:]
    return None


def _get_nested(obj: Any, dotted: str) -> Any:
    """Walk obj by '.' path. Treats numeric path components as either int index
    (for lists) or stringified-int dict keys (e.g. action_mix uses '0','1',...).
    Returns _MISSING (not None) for absent keys so callers can distinguish
    "key not present" from "key present with null value"."""
    cur = obj
    for part in dotted.split('.'):
        if cur is _MISSING:
            return _MISSING
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        elif isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            elif part.isdigit() and int(part) in cur:
                cur = cur[int(part)]
            else:
                return _MISSING
        else:
            return _MISSING
    return cur


def _evaluate_single_gate(field_name: str, op: str, threshold: Any,
                          metrics: dict | None) -> tuple[bool, str]:
    if metrics is None:
        return False, f'{field_name}: no metrics_file loaded'
    val = _get_nested(metrics, field_name)
    if val is _MISSING:
        return False, f'{field_name}: key missing from metrics_file'
    # val may legitimately be None (e.g. hard_stop_reason=null in success case).
    try:
        if op == 'eq':
            ok = val == threshold
        elif op == 'lt':
            ok = float(val) < float(threshold)
        elif op == 'gt':
            ok = float(val) > float(threshold)
        elif op == 'lte':
            ok = float(val) <= float(threshold)
        elif op == 'gte':
            ok = float(val) >= float(threshold)
        else:
            return False, f'{field_name}: unknown op {op}'
    except (TypeError, ValueError) as e:
        return False, f'{field_name}: type error comparing {val!r} {op} {threshold!r} ({e})'
    return ok, f'{field_name} ({val!r} {op} {threshold!r}) = {ok}'


def _load_metrics_file(stage: dict) -> dict | None:
    mf = stage.get('metrics_file')
    if not mf:
        return None
    p = REPO_ROOT / mf
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None


def evaluate_pass_gates(stage: dict) -> tuple[list[dict], list[dict]]:
    """Returns (passed, failed) lists of gate-record dicts."""
    passed, failed = [], []
    pass_spec = stage.get('pass') or {}
    metrics = _load_metrics_file(stage)
    for key, val in pass_spec.items():
        # Special non-suffixed gate: report_file_exists -> path string
        if key == 'report_file_exists':
            p = REPO_ROOT / str(val)
            ok = p.exists()
            rec = {'key': key, 'value': str(val), 'passed': ok,
                   'message': f'report_file_exists({val}) = {ok}'}
            (passed if ok else failed).append(rec)
            continue
        split = _split_gate_key(key)
        if split is None:
            failed.append({'key': key, 'passed': False,
                           'message': f'unparseable gate key {key!r}'})
            continue
        field_name, op = split
        ok, msg = _evaluate_single_gate(field_name, op, val, metrics)
        rec = {'key': key, 'value': val, 'passed': ok, 'message': msg}
        (passed if ok else failed).append(rec)
    return passed, failed


def evaluate_hard_stops(config: dict, stage: dict) -> list[dict]:
    """Returns list of triggered hard-stop records."""
    metrics = _load_metrics_file(stage)
    if metrics is None:
        return []
    triggered = []
    for hs in config.get('hard_stops', []) or []:
        val = _get_nested(metrics, hs['field'])
        if val is _MISSING or val is None:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        op, thr = hs['op'], float(hs['threshold'])
        fired = ((op == '>' and v > thr) or (op == '<' and v < thr) or
                 (op == '>=' and v >= thr) or (op == '<=' and v <= thr))
        if fired:
            triggered.append({**hs, 'value': v})
    return triggered


# ----------------------------------------------------------------------------
# Decision logic

def _runway_active(state: dict, config: dict) -> bool:
    rw = state.get('runway') or {}
    if not rw.get('active'):
        return False
    until = rw.get('approved_until')
    if until:
        try:
            # Parse ISO with timezone via fromisoformat fallback
            t_until = time.mktime(time.strptime(until.split('+')[0], '%Y-%m-%dT%H:%M:%S'))
            if time.time() > t_until:
                return False
        except Exception:
            pass
    budget = config.get('runway', {}).get('experiments_budget', 0)
    return rw.get('experiments_used', 0) < budget


def decide_next(state: dict, config: dict) -> StageResult:
    sid = state.get('current_stage_id')
    if not sid:
        return StageResult(stage_id='(none)', decision=Decision.ERROR,
                           reason='current_stage_id missing in state')

    stage = find_stage(config, sid)
    if stage is None:
        return StageResult(stage_id=sid, decision=Decision.ERROR,
                           reason=f'unknown stage id: {sid}')

    # decision_only stages return their configured decision verbatim.
    if stage.get('decision_only'):
        try:
            d = Decision(stage.get('decision', 'CONTINUE'))
        except ValueError:
            d = Decision.ERROR
        return StageResult(
            stage_id=sid, decision=d,
            reason=stage.get('reason') or stage.get('description', ''),
            command=None, next_stage=stage.get('next'),
        )

    # Command stage — classify by budget + runway.
    runtime_min = stage.get('expected_runtime_minutes', 0) or 0
    hands = stage.get('estimated_hands', 0) or 0
    budgets = config.get('budgets') or {}
    max_hands = budgets.get('max_hands_without_user', 5_000_000)
    max_runtime_h = budgets.get('max_runtime_hours_without_user', 8)

    cmd = stage.get('command')

    if hands > max_hands:
        return StageResult(stage_id=sid, decision=Decision.ASK_USER, command=cmd,
                           reason=f'estimated_hands {hands} > budget {max_hands}')
    if runtime_min > max_runtime_h * 60:
        return StageResult(stage_id=sid, decision=Decision.ASK_USER, command=cmd,
                           reason=f'expected_runtime {runtime_min}min > budget {max_runtime_h}h')

    if stage.get('requires_runway'):
        if not _runway_active(state, config):
            return StageResult(stage_id=sid, decision=Decision.ASK_USER, command=cmd,
                               reason='stage requires_runway=true and runway is not active')

    return StageResult(
        stage_id=sid, decision=Decision.CONTINUE, command=cmd,
        reason=(f'category={stage.get("category", "n/a")}, '
                f'~{runtime_min}min, ~{hands} hands; within budget'),
    )


# ----------------------------------------------------------------------------
# Execution

def _new_run_id(stage_id: str) -> str:
    return time.strftime('%Y%m%dT%H%M%S') + '_' + stage_id


def _write_run_report(run_dir: Path, stage: dict, result: StageResult,
                      *, dry_run: bool) -> None:
    lines = [
        f'# Autopilot run: {stage.get("id", "(unknown)")}',
        '',
        f'**Decision**: {result.decision.value}',
        f'**Dry-run**: {dry_run}',
        f'**Reason**: {result.reason}',
        f'**Runtime**: '
        + (f'{result.runtime_s:.1f}s' if result.runtime_s is not None else 'n/a'),
        '',
        '## Command',
        '```',
        (stage.get('command') or '(decision_only — no command)'),
        '```',
        '',
    ]
    if result.pass_gates:
        lines.append('## Gates passed')
        for g in result.pass_gates:
            lines.append(f'- {g.get("message", g)}')
        lines.append('')
    if result.fail_gates:
        lines.append('## Gates FAILED')
        for g in result.fail_gates:
            lines.append(f'- {g.get("message", g)}')
        lines.append('')
    if result.hard_stops_triggered:
        lines.append('## HARD-STOP TRIGGERED')
        for hs in result.hard_stops_triggered:
            lines.append(f'- {hs["id"]}: {hs["reason"]} (value={hs.get("value")})')
        lines.append('')
    if result.next_stage:
        lines.append(f'**Next stage**: {result.next_stage}')
    lines.append(f'**Human approval required**: '
                 f'{result.decision == Decision.ASK_USER}')
    (run_dir / 'report.md').write_text('\n'.join(lines), encoding='utf-8')

    # Also save a structured decision.json for machine reads.
    payload = {
        'stage_id': result.stage_id,
        'decision': result.decision.value,
        'reason': result.reason,
        'runtime_s': result.runtime_s,
        'dry_run': dry_run,
        'pass_gates': result.pass_gates,
        'fail_gates': result.fail_gates,
        'hard_stops_triggered': result.hard_stops_triggered,
        'next_stage': result.next_stage,
        'timestamp': _now_iso(),
    }
    (run_dir / 'decision.json').write_text(
        json.dumps(payload, indent=2, default=str), encoding='utf-8'
    )


def _append_history(state: dict, result: StageResult, run_id: str,
                    from_stage: str) -> None:
    state['history'].append({
        'run_id': run_id,
        'from_stage': from_stage,
        'decision': result.decision.value,
        'runtime_s': result.runtime_s,
        'next_stage': result.next_stage,
        'pass_gates_n': len(result.pass_gates),
        'fail_gates_n': len(result.fail_gates),
        'hard_stops_n': len(result.hard_stops_triggered),
        'timestamp': _now_iso(),
    })


def run_stage(state: dict, config: dict, *, dry_run: bool = False) -> StageResult:
    result = decide_next(state, config)
    sid = result.stage_id
    stage = find_stage(config, sid)
    if stage is None:
        return result

    run_id = _new_run_id(sid)
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result.run_id = run_id

    # decision_only branch
    if stage.get('decision_only'):
        if result.decision == Decision.CONTINUE:
            next_id = stage.get('next')
            result.next_stage = next_id
            if not dry_run:
                state['current_stage_id'] = next_id or sid
                _append_history(state, result, run_id, from_stage=sid)
                save_state(state)
        _write_run_report(run_dir, stage, result, dry_run=dry_run)
        return result

    # Command stage — only execute if CONTINUE.
    if result.decision != Decision.CONTINUE:
        _write_run_report(run_dir, stage, result, dry_run=dry_run)
        return result

    cmd = stage.get('command')
    if not cmd:
        result.decision = Decision.ERROR
        result.reason = f'stage {sid} has no command and is not decision_only'
        _write_run_report(run_dir, stage, result, dry_run=dry_run)
        return result

    (run_dir / 'command.txt').write_text(cmd, encoding='utf-8')

    if dry_run:
        # Preview the assumed-pass path so run-until-stop can chain.
        result.next_stage = stage.get('pass_next')
        result.reason = (f'DRY-RUN: would execute; preview next = '
                         f'{result.next_stage or "(none)"}')
        result.runtime_s = 0.0
        _write_run_report(run_dir, stage, result, dry_run=True)
        return result

    # Real execution.
    timeout_s = max(60, int((stage.get('expected_runtime_minutes', 60) or 60) * 60 * 3))
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=str(REPO_ROOT), timeout=timeout_s,
        )
        elapsed = time.time() - t0
        (run_dir / 'stdout.log').write_text(proc.stdout or '', encoding='utf-8')
        (run_dir / 'stderr.log').write_text(proc.stderr or '', encoding='utf-8')
        result.runtime_s = elapsed
        if proc.returncode != 0:
            result.decision = Decision.ERROR
            result.reason = (f'command exited {proc.returncode}; '
                             f'see {run_dir / "stderr.log"}')
            _append_history(state, result, run_id, from_stage=sid)
            save_state(state)
            _write_run_report(run_dir, stage, result, dry_run=False)
            return result
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        result.decision = Decision.ERROR
        result.reason = f'timed out after {elapsed:.0f}s (limit {timeout_s}s)'
        result.runtime_s = elapsed
        _append_history(state, result, run_id, from_stage=sid)
        save_state(state)
        _write_run_report(run_dir, stage, result, dry_run=False)
        return result

    # Hard-stop check first — overrides pass/fail gates.
    hs = evaluate_hard_stops(config, stage)
    if hs:
        result.decision = Decision.STOP
        result.hard_stops_triggered = hs
        result.reason = f'{len(hs)} hard-stop(s) triggered: ' + '; '.join(
            x['id'] for x in hs)
        result.next_stage = None
        _append_history(state, result, run_id, from_stage=sid)
        save_state(state)
        _write_run_report(run_dir, stage, result, dry_run=False)
        return result

    # Pass-gate evaluation.
    passed, failed = evaluate_pass_gates(stage)
    result.pass_gates = passed
    result.fail_gates = failed

    if failed:
        next_id = stage.get('fail_next') or sid
        result.reason = (f'{len(failed)} gate(s) failed; '
                         f'{len(passed)} passed; advancing to {next_id}')
    else:
        next_id = stage.get('pass_next') or sid
        result.reason = (f'all {len(passed)} pass-gate(s) ok; '
                         f'advancing to {next_id}')
    result.next_stage = next_id

    # Count experiments against runway budget.
    if (state.get('runway') or {}).get('active') and stage.get('category') in (
            'smoke', 'experiment', 'training'):
        state['runway']['experiments_used'] = (
            state['runway'].get('experiments_used', 0) + 1)

    state['current_stage_id'] = next_id or sid
    _append_history(state, result, run_id, from_stage=sid)
    save_state(state)
    _write_run_report(run_dir, stage, result, dry_run=False)
    return result


# ----------------------------------------------------------------------------
# CLI handlers

def cmd_status(args) -> int:
    config = load_config()
    state = load_state()
    sid = state.get('current_stage_id')
    stage = find_stage(config, sid)
    print('== Autopilot status ==')
    print(f'Config file   : {CONFIG_PATH}')
    print(f'State file    : {STATE_PATH}')
    print(f'Current stage : {sid}')
    if stage:
        print(f'  description  : {stage.get("description", "")}')
        print(f'  category     : {stage.get("category", "n/a")}')
        print(f'  runtime est  : {stage.get("expected_runtime_minutes", "n/a")} min')
        print(f'  decision_only: {bool(stage.get("decision_only"))}')
    rw = state.get('runway', {})
    print(f'Runway active : {bool(rw.get("active"))}'
          f' (used {rw.get("experiments_used", 0)}/'
          f'{config.get("runway", {}).get("experiments_budget", "?")})')
    if rw.get('approved_until'):
        print(f'Runway expires: {rw["approved_until"]}')
    hist = state.get('history', [])
    print(f'Decisions made: {len(hist)}')
    if hist:
        last = hist[-1]
        print(f'Last decision : {last["decision"]} on {last["from_stage"]} '
              f'(run_id={last["run_id"]})')
    return 0


def cmd_next(args) -> int:
    config = load_config()
    state = load_state()
    r = decide_next(state, config)
    print(f'Decision : {r.decision.value}')
    print(f'Stage    : {r.stage_id}')
    print(f'Reason   : {r.reason}')
    if r.command:
        print(f'Command  : {r.command}')
    if r.next_stage:
        print(f'Next     : {r.next_stage}')
    return 0 if r.decision in (Decision.CONTINUE, Decision.ASK_USER) else 1


def cmd_run_once(args) -> int:
    config = load_config()
    state = load_state()
    r = run_stage(state, config, dry_run=args.dry_run)
    print(f'Decision : {r.decision.value}')
    print(f'Stage    : {r.stage_id}')
    print(f'Reason   : {r.reason}')
    if r.runtime_s is not None:
        print(f'Runtime  : {r.runtime_s:.1f}s')
    if r.run_id:
        print(f'Run id   : {r.run_id}')
        print(f'Report   : autopilot_runs/{r.run_id}/report.md')
    if r.next_stage:
        print(f'Next     : {r.next_stage}')
    return 0 if r.decision in (Decision.CONTINUE, Decision.ASK_USER) else 1


def cmd_run_until_stop(args) -> int:
    config = load_config()
    # Dry-run does not persist state, so we keep an in-memory copy and advance
    # it ourselves between iterations to simulate the full chain.
    state = load_state()
    n = 0
    while n < args.max_steps:
        r = run_stage(state, config, dry_run=args.dry_run)
        n += 1
        print(f'[{n}/{args.max_steps}] {r.decision.value} '
              f'{r.stage_id} -> {r.next_stage or "(none)"}: {r.reason}')
        if r.decision in (Decision.ASK_USER, Decision.STOP, Decision.ERROR):
            print(f'Loop end: {r.decision.value}')
            return 0 if r.decision == Decision.ASK_USER else 1
        if args.dry_run:
            # run_stage skipped state mutation in dry-run mode; simulate
            # the advance in our in-memory copy so the next iteration sees
            # the next stage.
            if r.next_stage:
                state['current_stage_id'] = r.next_stage
            else:
                print('Loop end: dry-run produced no next_stage; stopping.')
                return 0
        else:
            # Non-dry-run already persisted; reload to pick up any external edits.
            state = load_state()
    print(f'Hit max_steps={args.max_steps}; stopping.')
    return 0


def cmd_explain(args) -> int:
    config = load_config()
    print('== Project ==')
    for k, v in (config.get('project') or {}).items():
        print(f'  {k}: {v}')
    print()
    print('== Current ==')
    for k, v in (config.get('current') or {}).items():
        print(f'  {k}: {v}')
    print()
    print('== Budgets ==')
    for k, v in (config.get('budgets') or {}).items():
        print(f'  {k}: {v}')
    print()
    print('== Runway (config defaults) ==')
    for k, v in (config.get('runway') or {}).items():
        if k == 'not_allowed':
            print(f'  {k}:')
            for x in v:
                print(f'    - {x}')
        else:
            print(f'  {k}: {v}')
    print()
    print('== Must-ask-user triggers ==')
    for x in (config.get('must_ask_user') or []):
        print(f'  - {x}')
    print()
    print('== Hard-stop gates ==')
    for hs in (config.get('hard_stops') or []):
        print(f'  - {hs["id"]}: {hs["field"]} {hs["op"]} {hs["threshold"]}'
              f'  ({hs["reason"]})')
    print()
    print('== Stages ==')
    for s in (config.get('stages') or []):
        kind = 'decision_only' if s.get('decision_only') else 'command'
        d = s.get('decision', '')
        rw = ' [runway]' if s.get('requires_runway') else ''
        print(f'  [{kind:13s}]{rw} {s["id"]} -> {d or "(gates)"}: '
              f'{s.get("description", "")}')
    return 0


def cmd_reset_state(args) -> int:
    if not args.confirm:
        print('Refusing to reset without --confirm.', file=sys.stderr)
        return 1
    save_state(new_state())
    print('State reset to bootstrap.')
    return 0


def cmd_approve_runway(args) -> int:
    if not args.confirm:
        print('Refusing to approve runway without --confirm.', file=sys.stderr)
        return 1
    state = load_state()
    config = load_config()
    state.setdefault('runway', {})
    state['runway']['active'] = True
    state['runway']['approved_at'] = _now_iso()
    until_t = time.time() + args.hours * 3600
    state['runway']['approved_until'] = time.strftime(
        '%Y-%m-%dT%H:%M:%S%z', time.localtime(until_t))
    state['runway']['experiments_used'] = state['runway'].get('experiments_used', 0)
    save_state(state)
    budget = config.get('runway', {}).get('experiments_budget', '?')
    print(f'Runway active until {state["runway"]["approved_until"]} '
          f'(budget {budget} experiments).')
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Phase 2 autopilot orchestrator')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('status').set_defaults(func=cmd_status)
    sub.add_parser('next').set_defaults(func=cmd_next)
    sub.add_parser('explain').set_defaults(func=cmd_explain)

    p_ro = sub.add_parser('run-once')
    p_ro.add_argument('--dry-run', action='store_true')
    p_ro.set_defaults(func=cmd_run_once)

    p_rs = sub.add_parser('run-until-stop')
    p_rs.add_argument('--dry-run', action='store_true')
    p_rs.add_argument('--max-steps', type=int, default=10)
    p_rs.set_defaults(func=cmd_run_until_stop)

    p_rr = sub.add_parser('reset-state')
    p_rr.add_argument('--confirm', action='store_true')
    p_rr.set_defaults(func=cmd_reset_state)

    p_ar = sub.add_parser('approve-runway')
    p_ar.add_argument('--confirm', action='store_true')
    p_ar.add_argument('--hours', type=int, default=24)
    p_ar.set_defaults(func=cmd_approve_runway)

    args = ap.parse_args(argv)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
