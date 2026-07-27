#!/usr/bin/env python3
"""
Monitor an AlphaHoldem V5 from-zero run.

Reads run_manifest.json and latest_train.log, then writes:
  - health_status.json
  - health_status.md

This is intentionally read-only with respect to training. It does not start,
stop, or mutate the trainer process.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path


LOG_RE = re.compile(
    r"\[\s*(?P<iteration>\d+)\]\s+"
    r"hands=(?P<hands>[\d,]+)\s+"
    r"rew=(?P<rew>[+-]?\d+(?:\.\d+)?)\s+"
    r"rew100=(?P<rew100>[+-]?\d+(?:\.\d+)?)\s+"
    r"ploss=(?P<ploss>[+-]?\d+(?:\.\d+)?)\s+"
    r"vloss=(?P<vloss>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?:vloss_bb2=[+-]?\d+(?:\.\d+)?\s+)?"
    r"ent=(?P<entropy>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?:kl=(?P<approx_kl>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"(?:ep=\d+/\d+\s+)?"
    r"(?:klstop=[01]\s+)?"
    r"(?:clipfrac=(?P<clip_frac>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"(?:d1bite=(?P<delta1_bite_frac>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"(?:aprior=(?P<action_prior_loss>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"(?:(?:r50=(?P<ratio_p50>[+-]?\d+(?:\.\d+)?)/)"
    r"(?:r95=(?P<ratio_p95>[+-]?\d+(?:\.\d+)?)/)"
    r"(?:r99=(?P<ratio_p99>[+-]?\d+(?:\.\d+)?)/)"
    r"(?:rmax=(?P<ratio_max>[+-]?\d+(?:\.\d+)?)\s+))?"
    r"eps=(?P<epsilon>[+-]?\d+(?:\.\d+)?)\s+"
    r"pool=(?P<pool>\d+)\s+"
    r"(?:mirror=(?P<mirror_replay_hands>\d+)/(?P<mirror_source_hands>\d+)\s+)?"
    r"(?:aiev=(?P<allin_ev_replacements>\d+):(?P<allin_ev_runouts>\d+)\s+)?"
    r"(?:aiev_skip=(?P<allin_ev_skipped_hands>\d+):(?P<allin_ev_skipped_runouts>\d+)\s+)?"
    r"trans=(?P<trans>\d+)\s+"
    r"(?:terms=(?P<terms>\d+)\s+)?"
    r"(?:mix=F(?P<mix_fold>[+-]?\d+(?:\.\d+)?)/C(?P<mix_call>[+-]?\d+(?:\.\d+)?)/R(?P<mix_raise>[+-]?\d+(?:\.\d+)?)/A(?P<mix_allin>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"(?:pmix=F(?P<pmix_fold>[+-]?\d+(?:\.\d+)?)/C(?P<pmix_call>[+-]?\d+(?:\.\d+)?)/R(?P<pmix_raise>[+-]?\d+(?:\.\d+)?)/A(?P<pmix_allin>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"(?:xmix=F(?P<xmix_fold>[+-]?\d+(?:\.\d+)?)/C(?P<xmix_call>[+-]?\d+(?:\.\d+)?)/R(?P<xmix_raise>[+-]?\d+(?:\.\d+)?)/A(?P<xmix_allin>[+-]?\d+(?:\.\d+)?)\s+)?"
    r"h/s=(?P<hps>[+-]?\d+(?:\.\d+)?)\s+"
    r"tdec/s=(?P<tdecps>[+-]?\d+(?:\.\d+)?)\s+"
    r"inf_bs=(?P<inf_bs>[+-]?\d+(?:\.\d+)?)\s+"
    r"collect=(?P<collect>[+-]?\d+(?:\.\d+)?)s\s+"
    r"ppo=(?P<ppo>[+-]?\d+(?:\.\d+)?)s"
)


def parse_log(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = LOG_RE.search(line)
        if not m:
            continue
        d = m.groupdict()
        def optional_float(key: str) -> float | None:
            value = d.get(key)
            return float(value) if value is not None else None

        mix = None
        if d.get('mix_fold') is not None:
            mix = {
                'fold': float(d['mix_fold']),
                'call': float(d['mix_call']),
                'raise': float(d['mix_raise']),
                'allin': float(d['mix_allin']),
            }
        preflop_mix = None
        if d.get('pmix_fold') is not None:
            preflop_mix = {
                'fold': float(d['pmix_fold']),
                'call': float(d['pmix_call']),
                'raise': float(d['pmix_raise']),
                'allin': float(d['pmix_allin']),
            }
        postflop_mix = None
        if d.get('xmix_fold') is not None:
            postflop_mix = {
                'fold': float(d['xmix_fold']),
                'call': float(d['xmix_call']),
                'raise': float(d['xmix_raise']),
                'allin': float(d['xmix_allin']),
            }
        exp003_metrics = None
        if d.get('mirror_replay_hands') is not None or d.get('allin_ev_replacements') is not None:
            exp003_metrics = {
                'mirror_replay_hands': int(d.get('mirror_replay_hands') or 0),
                'mirror_source_hands': int(d.get('mirror_source_hands') or 0),
                'allin_ev_replacements': int(d.get('allin_ev_replacements') or 0),
                'allin_ev_runouts': int(d.get('allin_ev_runouts') or 0),
                'allin_ev_skipped_hands': int(d.get('allin_ev_skipped_hands') or 0),
                'allin_ev_skipped_runouts': int(d.get('allin_ev_skipped_runouts') or 0),
            }
        rows.append({
            'iteration': int(d['iteration']),
            'hands': int(d['hands'].replace(',', '')),
            'reward': float(d['rew']),
            'reward_window_100': float(d['rew100']),
            'policy_loss': float(d['ploss']),
            'value_loss': float(d['vloss']),
            'entropy': float(d['entropy']),
            'approx_kl': optional_float('approx_kl'),
            'clip_frac': optional_float('clip_frac'),
            'delta1_bite_frac': optional_float('delta1_bite_frac'),
            'action_prior_loss': optional_float('action_prior_loss'),
            'ratio_p50': optional_float('ratio_p50'),
            'ratio_p95': optional_float('ratio_p95'),
            'ratio_p99': optional_float('ratio_p99'),
            'ratio_max': optional_float('ratio_max'),
            'epsilon': float(d['epsilon']),
            'pool_size': int(d['pool']),
            'transitions': int(d['trans']),
            'terminal_trajectories': int(d['terms']) if d.get('terms') else None,
            'action_mix': mix,
            'preflop_action_mix': preflop_mix,
            'postflop_action_mix': postflop_mix,
            'exp003_metrics': exp003_metrics,
            'hands_per_second': float(d['hps']),
            'trainable_decisions_per_second': float(d['tdecps']),
            'inference_batch_size': float(d['inf_bs']),
            'collect_seconds': float(d['collect']),
            'ppo_seconds': float(d['ppo']),
            'raw': line,
        })
    return rows


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def load_json_object_with_retry(
    path: Path,
    attempts: int = 5,
    sleep_seconds: float = 0.1,
) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, None
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            text = path.read_text(encoding='utf-8')
            if not text.strip():
                last_error = f'{path.name} is empty'
            else:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    return obj, None
                last_error = f'{path.name} decoded as {type(obj).__name__}, expected object'
        except Exception as exc:
            last_error = f'{type(exc).__name__}: {exc}'
        if attempt + 1 < attempts:
            time.sleep(sleep_seconds)
    return {}, last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--tail', type=int, default=20)
    parser.add_argument('--stale-minutes', type=float, default=30.0)
    parser.add_argument('--entropy-hard-stop', type=float, default=0.10)
    parser.add_argument('--entropy-warn', type=float, default=0.30)
    parser.add_argument('--value-loss-hard-stop', type=float, default=50000.0)
    parser.add_argument('--min-hps-warn', type=float, default=250.0)
    parser.add_argument('--mix-dominance-warn', type=float, default=0.90)
    parser.add_argument('--mix-dominance-fail', type=float, default=0.97)
    parser.add_argument('--allin-warn', type=float, default=0.15)
    parser.add_argument('--allin-fail', type=float, default=0.30)
    parser.add_argument('--raise-floor-warn-after-iter', type=int, default=200)
    parser.add_argument('--raise-floor-warn', type=float, default=0.01)
    parser.add_argument('--preflop-call-warn-after-iter', type=int, default=200)
    parser.add_argument('--preflop-call-warn', type=float, default=0.03)
    parser.add_argument('--preflop-call-fail', type=float, default=0.005)
    parser.add_argument('--preflop-dominance-warn', type=float, default=0.90)
    parser.add_argument('--preflop-dominance-fail', type=float, default=0.97)
    parser.add_argument('--preflop-allin-warn', type=float, default=0.12)
    parser.add_argument('--preflop-allin-fail', type=float, default=0.25)
    parser.add_argument('--postflop-guard-warn-after-iter', type=int, default=200)
    parser.add_argument('--postflop-raise-allin-warn', type=float, default=0.72)
    parser.add_argument('--postflop-raise-allin-fail', type=float, default=0.88)
    parser.add_argument('--postflop-call-warn', type=float, default=0.08)
    parser.add_argument('--postflop-call-fail', type=float, default=0.03)
    parser.add_argument('--stderr-recent-minutes', type=float, default=5.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    manifest_path = run_dir / 'run_manifest.json'
    log_path = run_dir / 'latest_train.log'
    stderr_path = run_dir / 'console.err.log'

    manifest, manifest_error = load_json_object_with_retry(manifest_path)

    rows = parse_log(log_path)
    latest = rows[-1] if rows else None
    recent = rows[-args.tail:] if rows else []

    now = datetime.now(timezone.utc)
    checks: list[dict] = []

    def add_check(name: str, status: str, detail: str):
        checks.append({'name': name, 'status': status, 'detail': detail})

    if not rows:
        add_check('training_log', 'WARN', f'No parsed iterations in {log_path}')
    else:
        add_check('training_log', 'PASS', f'Parsed {len(rows)} iterations')

    if manifest_error:
        add_check('manifest', 'WARN', f'run_manifest.json unavailable or partial: {manifest_error}')
    elif manifest_path.exists():
        add_check('manifest', 'PASS', 'run_manifest.json loaded')

    config = manifest.get('config', {}) if isinstance(manifest.get('config', {}), dict) else {}
    env_version = str(config.get('env_version') or manifest.get('env_version') or '')
    if not env_version:
        add_check('environment', 'WARN', 'No env_version metadata; cannot prove fixed 200bb V5 environment')
    elif env_version == 'v55':
        add_check('environment', 'PASS', 'env_version=v55')
    else:
        add_check('environment', 'WARN', f'env_version={env_version}; this is a recorded deviation from fixed-env V5')

    if latest:
        ent = latest['entropy']
        if ent < args.entropy_hard_stop:
            add_check('entropy', 'FAIL', f'entropy {ent:.4f} < hard stop {args.entropy_hard_stop}')
        elif ent < args.entropy_warn:
            add_check('entropy', 'WARN', f'entropy {ent:.4f} < warn {args.entropy_warn}')
        else:
            add_check('entropy', 'PASS', f'entropy {ent:.4f}')

        vloss = latest['value_loss']
        if vloss > args.value_loss_hard_stop:
            add_check('value_loss', 'FAIL', f'value_loss {vloss:.1f} > {args.value_loss_hard_stop:.1f}')
        else:
            add_check('value_loss', 'PASS', f'value_loss {vloss:.1f}')

        hps = latest['hands_per_second']
        if hps < args.min_hps_warn:
            add_check('throughput', 'WARN', f'hands/sec {hps:.1f} < {args.min_hps_warn:.1f}')
        else:
            add_check('throughput', 'PASS', f'hands/sec {hps:.1f}')

        if latest['iteration'] >= int(manifest.get('config', {}).get('snapshot_every', 200)):
            if latest['pool_size'] <= 0:
                add_check('opponent_pool', 'WARN', 'Past snapshot iteration but pool is empty')
            else:
                add_check('opponent_pool', 'PASS', f"pool size {latest['pool_size']}")
        else:
            add_check('opponent_pool', 'PASS', f"pre-snapshot phase, pool size {latest['pool_size']}")

        mix = latest.get('action_mix')
        if mix is None:
            add_check('action_mix', 'WARN', 'No action mix in latest log line')
        else:
            dominant = max(('fold', 'call', 'raise'), key=lambda k: mix[k])
            dominant_value = mix[dominant]
            if dominant_value >= args.mix_dominance_fail:
                add_check('action_mix', 'FAIL', f"{dominant} dominates at {dominant_value:.3f}")
            elif dominant_value >= args.mix_dominance_warn:
                add_check('action_mix', 'WARN', f"{dominant} dominates at {dominant_value:.3f}")
            elif mix['allin'] >= args.allin_fail:
                add_check('action_mix', 'FAIL', f"all-in frequency {mix['allin']:.3f}")
            elif mix['allin'] >= args.allin_warn:
                add_check('action_mix', 'WARN', f"all-in frequency {mix['allin']:.3f}")
            elif latest['iteration'] >= args.raise_floor_warn_after_iter and mix['raise'] < args.raise_floor_warn:
                add_check('action_mix', 'WARN', f"raise frequency {mix['raise']:.3f}")
            else:
                add_check(
                    'action_mix',
                    'PASS',
                    f"F={mix['fold']:.3f} C={mix['call']:.3f} R={mix['raise']:.3f} A={mix['allin']:.3f}",
                )

        preflop_mix = latest.get('preflop_action_mix')
        if preflop_mix is not None:
            preflop_dominant = max(('fold', 'call', 'raise'), key=lambda k: preflop_mix[k])
            preflop_dominant_value = preflop_mix[preflop_dominant]
            if preflop_dominant_value >= args.preflop_dominance_fail:
                add_check(
                    'preflop_action_mix',
                    'FAIL',
                    f"{preflop_dominant} dominates preflop at {preflop_dominant_value:.3f}",
                )
            elif preflop_mix['allin'] >= args.preflop_allin_fail:
                add_check(
                    'preflop_action_mix',
                    'FAIL',
                    f"preflop all-in frequency {preflop_mix['allin']:.3f}",
                )
            elif (
                latest['iteration'] >= args.preflop_call_warn_after_iter
                and preflop_mix['call'] <= args.preflop_call_fail
            ):
                add_check(
                    'preflop_action_mix',
                    'FAIL',
                    f"preflop call/check frequency {preflop_mix['call']:.3f} <= {args.preflop_call_fail:.3f}",
                )
            elif preflop_dominant_value >= args.preflop_dominance_warn:
                add_check(
                    'preflop_action_mix',
                    'WARN',
                    f"{preflop_dominant} dominates preflop at {preflop_dominant_value:.3f}",
                )
            elif preflop_mix['allin'] >= args.preflop_allin_warn:
                add_check(
                    'preflop_action_mix',
                    'WARN',
                    f"preflop all-in frequency {preflop_mix['allin']:.3f}",
                )
            elif (
                latest['iteration'] >= args.preflop_call_warn_after_iter
                and preflop_mix['call'] <= args.preflop_call_warn
            ):
                add_check(
                    'preflop_action_mix',
                    'WARN',
                    f"preflop call/check frequency {preflop_mix['call']:.3f} <= {args.preflop_call_warn:.3f}",
                )
            else:
                add_check(
                    'preflop_action_mix',
                    'PASS',
                    f"F={preflop_mix['fold']:.3f} C={preflop_mix['call']:.3f} "
                    f"R={preflop_mix['raise']:.3f} A={preflop_mix['allin']:.3f}",
                )

        postflop_mix = latest.get('postflop_action_mix')
        if postflop_mix is not None and latest['iteration'] >= args.postflop_guard_warn_after_iter:
            postflop_raise_allin = postflop_mix['raise'] + postflop_mix['allin']
            if postflop_raise_allin >= args.postflop_raise_allin_fail:
                add_check(
                    'postflop_action_mix',
                    'FAIL',
                    f"postflop raise+all-in {postflop_raise_allin:.3f} >= {args.postflop_raise_allin_fail:.3f}",
                )
            elif postflop_mix['call'] <= args.postflop_call_fail:
                add_check(
                    'postflop_action_mix',
                    'FAIL',
                    f"postflop call/check frequency {postflop_mix['call']:.3f} <= {args.postflop_call_fail:.3f}",
                )
            elif postflop_raise_allin >= args.postflop_raise_allin_warn:
                add_check(
                    'postflop_action_mix',
                    'WARN',
                    f"postflop raise+all-in {postflop_raise_allin:.3f} >= {args.postflop_raise_allin_warn:.3f}",
                )
            elif postflop_mix['call'] <= args.postflop_call_warn:
                add_check(
                    'postflop_action_mix',
                    'WARN',
                    f"postflop call/check frequency {postflop_mix['call']:.3f} <= {args.postflop_call_warn:.3f}",
                )
            else:
                add_check(
                    'postflop_action_mix',
                    'PASS',
                    f"F={postflop_mix['fold']:.3f} C={postflop_mix['call']:.3f} "
                    f"R={postflop_mix['raise']:.3f} A={postflop_mix['allin']:.3f} "
                    f"RA={postflop_raise_allin:.3f}",
                )

        recent_mixes = [r.get('action_mix') for r in recent if r.get('action_mix') is not None]
        if recent_mixes:
            max_allin = max(m['allin'] for m in recent_mixes)
            mean_allin = statistics.fmean(m['allin'] for m in recent_mixes)
            max_dominance = max(max(m['fold'], m['call'], m['raise']) for m in recent_mixes)
            last3 = recent_mixes[-3:]
            last3_hard = any(
                m['allin'] >= args.allin_fail
                or max(m['fold'], m['call'], m['raise']) >= args.mix_dominance_fail
                for m in last3
            )
            if last3_hard:
                add_check(
                    'action_mix_recent',
                    'FAIL',
                    f'recent hard collapse signal: max all-in {max_allin:.3f}, max dominance {max_dominance:.3f}',
                )
            elif max_allin >= args.allin_fail:
                add_check(
                    'action_mix_recent',
                    'WARN',
                    f'all-in spike in recent window: max {max_allin:.3f}',
                )
            elif mean_allin >= args.allin_warn:
                add_check(
                    'action_mix_recent',
                    'WARN',
                    f'recent mean all-in {mean_allin:.3f}',
                )
            elif max_dominance >= args.mix_dominance_warn:
                add_check(
                    'action_mix_recent',
                    'WARN',
                    f'action dominance spike in recent window: max {max_dominance:.3f}',
                )
            else:
                add_check(
                    'action_mix_recent',
                    'PASS',
                    f'max all-in {max_allin:.3f}, mean all-in {mean_allin:.3f}, max dominance {max_dominance:.3f}',
                )

        recent_postflop_mixes = [
            r.get('postflop_action_mix') for r in recent if r.get('postflop_action_mix') is not None
        ]
        if recent_postflop_mixes and latest['iteration'] >= args.postflop_guard_warn_after_iter:
            raise_allin_values = [m['raise'] + m['allin'] for m in recent_postflop_mixes]
            call_values = [m['call'] for m in recent_postflop_mixes]
            max_raise_allin = max(raise_allin_values)
            mean_raise_allin = statistics.fmean(raise_allin_values)
            min_call = min(call_values)
            mean_call = statistics.fmean(call_values)
            last3_postflop = recent_postflop_mixes[-3:]
            last3_hard = any(
                (m['raise'] + m['allin']) >= args.postflop_raise_allin_fail
                or m['call'] <= args.postflop_call_fail
                for m in last3_postflop
            )
            if last3_hard:
                add_check(
                    'postflop_action_mix_recent',
                    'FAIL',
                    f'recent hard postflop signal: max RA {max_raise_allin:.3f}, min call {min_call:.3f}',
                )
            elif max_raise_allin >= args.postflop_raise_allin_fail:
                add_check(
                    'postflop_action_mix_recent',
                    'WARN',
                    f'postflop raise+all-in spike in recent window: max {max_raise_allin:.3f}',
                )
            elif mean_raise_allin >= args.postflop_raise_allin_warn:
                add_check(
                    'postflop_action_mix_recent',
                    'WARN',
                    f'recent mean postflop raise+all-in {mean_raise_allin:.3f}',
                )
            elif min_call <= args.postflop_call_fail:
                add_check(
                    'postflop_action_mix_recent',
                    'WARN',
                    f'postflop call/check dip in recent window: min {min_call:.3f}',
                )
            elif mean_call <= args.postflop_call_warn:
                add_check(
                    'postflop_action_mix_recent',
                    'WARN',
                    f'recent mean postflop call/check {mean_call:.3f}',
                )
            else:
                add_check(
                    'postflop_action_mix_recent',
                    'PASS',
                    f'max RA {max_raise_allin:.3f}, mean RA {mean_raise_allin:.3f}, '
                    f'min call {min_call:.3f}, mean call {mean_call:.3f}',
                )

    if log_path.exists():
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc)
        age_min = (now - mtime).total_seconds() / 60.0
        if age_min > args.stale_minutes:
            add_check('staleness', 'FAIL', f'latest_train.log age {age_min:.1f} min')
        else:
            add_check('staleness', 'PASS', f'latest_train.log age {age_min:.1f} min')

    stderr_bytes = stderr_path.stat().st_size if stderr_path.exists() else 0
    if stderr_bytes > 0:
        stderr_mtime = datetime.fromtimestamp(stderr_path.stat().st_mtime, tz=timezone.utc)
        stderr_age_min = (now - stderr_mtime).total_seconds() / 60.0
        if stderr_age_min <= args.stderr_recent_minutes:
            add_check(
                'stderr',
                'WARN',
                f'console.err.log has {stderr_bytes} bytes; last write {stderr_age_min:.1f} min ago',
            )
        else:
            add_check(
                'stderr',
                'PASS',
                f'console.err.log has historical {stderr_bytes} bytes; last write {stderr_age_min:.1f} min ago',
            )
    else:
        add_check('stderr', 'PASS', 'console.err.log empty')

    overall = 'PASS'
    if any(c['status'] == 'FAIL' for c in checks):
        overall = 'FAIL'
    elif any(c['status'] == 'WARN' for c in checks):
        overall = 'WARN'

    summary = {
        'run_dir': str(run_dir),
        'run_id': manifest.get('run_id'),
        'checked_at': now.isoformat(),
        'overall': overall,
        'latest': latest,
        'recent_means': {
            'hands_per_second': mean([r['hands_per_second'] for r in recent]),
            'trainable_decisions_per_second': mean([r['trainable_decisions_per_second'] for r in recent]),
            'entropy': mean([r['entropy'] for r in recent]),
            'value_loss': mean([r['value_loss'] for r in recent]),
            'postflop_raise_allin': mean(
                [
                    m['raise'] + m['allin']
                    for m in (r.get('postflop_action_mix') for r in recent)
                    if m is not None
                ]
            ),
            'postflop_call': mean(
                [m['call'] for m in (r.get('postflop_action_mix') for r in recent) if m is not None]
            ),
        },
        'checks': checks,
    }

    (run_dir / 'health_status.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding='utf-8',
    )

    lines = [
        '# V5 Health Status',
        '',
        f"- Run id: `{summary['run_id']}`",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{overall}**",
    ]
    if latest:
        lines += [
            f"- Iteration: `{latest['iteration']}`",
            f"- Hands: `{latest['hands']:,}`",
            f"- Entropy: `{latest['entropy']:.4f}`",
            f"- Value loss: `{latest['value_loss']:.1f}`",
            f"- Hands/sec: `{latest['hands_per_second']:.1f}`",
            f"- Pool size: `{latest['pool_size']}`",
        ]
        if latest.get('clip_frac') is not None:
            lines += [
                f"- Approx KL: `{latest['approx_kl']:.4f}`",
                f"- PPO clip fraction: `{latest['clip_frac']:.3f}`",
                f"- Delta1 bite fraction: `{latest['delta1_bite_frac']:.3f}`",
                (
                    f"- Policy ratio quantiles: `r50={latest['ratio_p50']:.2f} "
                    f"r95={latest['ratio_p95']:.2f} r99={latest['ratio_p99']:.2f} "
                    f"rmax={latest['ratio_max']:.2f}`"
                ),
            ]
        if latest.get('action_prior_loss') is not None:
            lines.append(f"- Action prior loss: `{latest['action_prior_loss']:.4f}`")
        if latest.get('action_mix') is not None:
            mix = latest['action_mix']
            lines.append(
                f"- Action mix: `F={mix['fold']:.3f} C={mix['call']:.3f} "
                f"R={mix['raise']:.3f} A={mix['allin']:.3f}`"
            )
        if latest.get('preflop_action_mix') is not None:
            mix = latest['preflop_action_mix']
            lines.append(
                f"- Preflop action mix: `F={mix['fold']:.3f} C={mix['call']:.3f} "
                f"R={mix['raise']:.3f} A={mix['allin']:.3f}`"
            )
        if latest.get('postflop_action_mix') is not None:
            mix = latest['postflop_action_mix']
            lines.append(
                f"- Postflop action mix: `F={mix['fold']:.3f} C={mix['call']:.3f} "
                f"R={mix['raise']:.3f} A={mix['allin']:.3f}`"
            )
        lines += [
            '',
            'Latest log:',
            '',
            '```text',
            latest['raw'],
            '```',
        ]
    lines += ['', 'Checks:', '']
    for c in checks:
        lines.append(f"- {c['status']}: `{c['name']}` - {c['detail']}")
    lines.append('')
    (run_dir / 'health_status.md').write_text('\n'.join(lines), encoding='utf-8')

    print(f"{overall}: {run_dir}")
    if latest:
        print(latest['raw'])
    return 0 if overall != 'FAIL' else 2


if __name__ == '__main__':
    raise SystemExit(main())
