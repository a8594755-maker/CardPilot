#!/usr/bin/env python3
"""VALUE-AUDIT-001: reporting-only critic scale and calibration audit."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import torch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

from alpha_holdem.network import AlphaHoldemNet  # noqa: E402
from play_slumbot import (  # noqa: E402
    compute_commitments,
    compute_legal_mask,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values: np.ndarray, q: float) -> float | None:
    return float(np.quantile(values, q)) if values.size else None


def regression_metrics(predictions: list[float], targets: list[float]) -> dict[str, Any]:
    p = np.asarray(predictions, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    n = int(y.size)
    if n == 0:
        return {'n': 0}
    residual = y - p
    target_mean = float(y.mean())
    target_std = float(y.std(ddof=1)) if n > 1 else 0.0
    pred_mean = float(p.mean())
    pred_std = float(p.std(ddof=1)) if n > 1 else 0.0
    mse = float(np.mean(residual ** 2))
    rmse = math.sqrt(mse)
    target_var = float(np.var(y, ddof=1)) if n > 1 else 0.0
    residual_var = float(np.var(residual, ddof=1)) if n > 1 else 0.0
    explained_variance = 1.0 - residual_var / target_var if target_var > 0 else None
    slope = float(np.cov(p, y, ddof=1)[0, 1] / np.var(p, ddof=1)) if n > 1 and pred_std > 0 else None
    intercept = target_mean - slope * pred_mean if slope is not None else None
    corr = float(np.corrcoef(p, y)[0, 1]) if n > 1 and pred_std > 0 and target_std > 0 else None
    return {
        'n': n,
        'target_mean_bb': target_mean,
        'target_std_bb': target_std,
        'target_p01_bb': quantile(y, 0.01),
        'target_p50_bb': quantile(y, 0.50),
        'target_p99_bb': quantile(y, 0.99),
        'prediction_mean_bb': pred_mean,
        'prediction_std_bb': pred_std,
        'prediction_p01_bb': quantile(p, 0.01),
        'prediction_p50_bb': quantile(p, 0.50),
        'prediction_p99_bb': quantile(p, 0.99),
        'bias_bb': float(np.mean(p - y)),
        'mae_bb': float(np.mean(np.abs(residual))),
        'rmse_bb': rmse,
        'rmse_over_target_std': rmse / target_std if target_std > 0 else None,
        'prediction_std_over_target_std': pred_std / target_std if target_std > 0 else None,
        'explained_variance': explained_variance,
        'calibration_slope': slope,
        'calibration_intercept_bb': intercept,
        'pearson_r': corr,
    }


def pot_bucket(pot_bb: float) -> str:
    if pot_bb < 4:
        return 'lt4bb'
    if pot_bb < 10:
        return '4to10bb'
    if pot_bb < 40:
        return '10to40bb'
    return 'ge40bb'


def classify(global_metrics: dict[str, Any], strata: dict[str, dict[str, Any]]) -> dict[str, Any]:
    red_flags: list[str] = []
    ev = global_metrics.get('explained_variance')
    rmse_ratio = global_metrics.get('rmse_over_target_std')
    slope = global_metrics.get('calibration_slope')
    scale = global_metrics.get('prediction_std_over_target_std')
    bias = abs(float(global_metrics.get('bias_bb') or 0.0))
    target_std = float(global_metrics.get('target_std_bb') or 0.0)
    if ev is not None and ev < -0.05:
        red_flags.append('explained_variance_below_-0.05')
    if rmse_ratio is not None and rmse_ratio > 1.05:
        red_flags.append('rmse_over_target_std_above_1.05')
    if slope is not None and not 0.25 <= slope <= 2.5:
        red_flags.append('calibration_slope_outside_0.25_2.5')
    if scale is not None and not 0.05 <= scale <= 2.0:
        red_flags.append('prediction_scale_outside_0.05_2.0_target_std')
    if target_std > 0 and bias > 0.25 * target_std:
        red_flags.append('absolute_bias_above_0.25_target_std')
    supported_strata = 0
    for metric in strata.values():
        if int(metric.get('n') or 0) >= 500 and (
            (metric.get('explained_variance') is not None and metric['explained_variance'] < -0.05)
            or (metric.get('rmse_over_target_std') is not None and metric['rmse_over_target_std'] > 1.05)
        ):
            supported_strata += 1
    if len(red_flags) >= 2 and supported_strata >= 3:
        decision = 'SUPPORTS_CRITIC_OR_REWARD_SCALE_PROBLEM'
    elif not red_flags:
        decision = 'DOES_NOT_SUPPORT_CRITIC_OR_REWARD_SCALE_PROBLEM'
    else:
        decision = 'INCONCLUSIVE_CRITIC_SIGNAL'
    return {
        'decision': decision,
        'global_red_flags': red_flags,
        'supporting_strata_count': supported_strata,
        'route_pivot_exp_w1_eligible': decision == 'SUPPORTS_CRITIC_OR_REWARD_SCALE_PROBLEM',
        'exp_w1_registration_authorized_now': False,
        'authorization_condition': 'only after EXP005-C FAIL/INCONCLUSIVE or non-strong promotion enters route-pivot review, and only if W1 is the single selected route',
        'note': 'Reporting-only diagnostic; no automatic trainer change and no strength inference.',
    }


def load_model(checkpoint_path: Path, device: str):
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model = AlphaHoldemNet(num_actions=9, norm_layer=checkpoint.get('norm_layer', 'bn')).to(device)
    model.eval()
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(2, 2, device=device),
        )
    model.load_state_dict(checkpoint['model'])
    model.eval()
    return checkpoint, model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--dump-glob', required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--batch-size', type=int, default=512)
    parser.add_argument('--out-json', required=True)
    parser.add_argument('--out-md', required=True)
    args = parser.parse_args()

    if os.name == 'nt':
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    checkpoint_path = Path(args.checkpoint)
    checkpoint, model = load_model(checkpoint_path, args.device)
    dump_paths = [Path(path) for path in sorted(glob.glob(args.dump_glob))]
    if not dump_paths:
        raise FileNotFoundError(f'no dump files match {args.dump_glob}')

    predictions: list[float] = []
    targets: list[float] = []
    metadata: list[dict[str, Any]] = []
    cards_batch: list[np.ndarray] = []
    actions_batch: list[np.ndarray] = []
    extras_batch: list[np.ndarray] = []
    masks_batch: list[np.ndarray] = []
    batch_targets: list[float] = []
    batch_meta: list[dict[str, Any]] = []
    skipped = defaultdict(int)
    unique_hands: set[str] = set()

    def flush() -> None:
        if not cards_batch:
            return
        with torch.no_grad():
            _, values = model(
                torch.tensor(np.asarray(cards_batch), dtype=torch.float32, device=args.device),
                torch.tensor(np.asarray(actions_batch), dtype=torch.float32, device=args.device),
                torch.tensor(np.asarray(extras_batch), dtype=torch.float32, device=args.device),
                torch.tensor(np.asarray(masks_batch), dtype=torch.float32, device=args.device),
            )
        predictions.extend(float(value) for value in values.squeeze(-1).cpu().numpy())
        targets.extend(batch_targets)
        metadata.extend(batch_meta)
        cards_batch.clear(); actions_batch.clear(); extras_batch.clear(); masks_batch.clear()
        batch_targets.clear(); batch_meta.clear()

    for dump_path in dump_paths:
        part = dump_path.stem
        with dump_path.open('r', encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                unique_hands.add(f"{part}:{row.get('hand_idx')}")
                if row.get('who') != 'hero':
                    continue
                state = parse_action(str(row.get('action_str_before') or ''))
                if 'error' in state or int(state.get('pos', -1)) != int(row.get('mover_pos', -2)):
                    skipped['state_or_position_mismatch'] += 1
                    continue
                try:
                    client_pos = int(row['client_pos'])
                    street = int(row['street'])
                    card = encode_cards(row['hero_hole'], row.get('board') or [], street)
                    action = encode_action_history(state, client_pos, int(state['pos']), obs_version='v55')
                    commitments = compute_commitments(state)
                    stacks = [20000 - commitments['hero_total'], 20000 - commitments['opp_total']]
                    extra = encode_extra(stacks)
                    mask = compute_legal_mask(state)
                    target_bb = float(row['winnings_hero']) / 100.0
                    pot_bb = float(row.get('pot_before') or 0.0) / 100.0
                    allin = bool(
                        float(row.get('to_call') or 0.0) >= float(row.get('stack_remaining') or math.inf)
                        or float(row.get('street_last_bet_to') or 0.0) >= 20000
                        or (
                            row.get('action_move') == 'b'
                            and float(row.get('action_amount') or 0.0) >= 20000
                        )
                    )
                except Exception:  # noqa: BLE001
                    skipped['encoding_error'] += 1
                    continue
                cards_batch.append(card); actions_batch.append(action); extras_batch.append(extra); masks_batch.append(mask)
                batch_targets.append(target_bb)
                batch_meta.append({
                    'position': 'SB' if client_pos == 1 else 'BB',
                    'street': ('preflop', 'flop', 'turn', 'river')[street],
                    'pot_bucket': pot_bucket(pot_bb),
                    'allin_context': 'allin' if allin else 'not_allin',
                })
                if len(cards_batch) >= args.batch_size:
                    flush()
    flush()

    global_metrics = regression_metrics(predictions, targets)
    strata: dict[str, dict[str, Any]] = {}
    for dimension in ('position', 'street', 'pot_bucket', 'allin_context'):
        groups: dict[str, tuple[list[float], list[float]]] = {}
        for pred, target, meta in zip(predictions, targets, metadata):
            key = f'{dimension}:{meta[dimension]}'
            if key not in groups:
                groups[key] = ([], [])
            groups[key][0].append(pred); groups[key][1].append(target)
        for key, (preds, ys) in groups.items():
            strata[key] = regression_metrics(preds, ys)
    decision = classify(global_metrics, strata)
    payload = {
        'audit_id': 'VALUE-AUDIT-001',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'COMPLETED_REPORTING_ONLY',
        'checkpoint': {
            'path': str(checkpoint_path.resolve()),
            'sha256': sha256_path(checkpoint_path),
            'iteration': checkpoint.get('iteration'),
            'hands': checkpoint.get('total_hands'),
            'env_version': checkpoint.get('env_version'),
            'obs_version': checkpoint.get('obs_version'),
        },
        'dataset': {
            'dump_glob': args.dump_glob,
            'files': len(dump_paths),
            'file_sha256': {path.name: sha256_path(path) for path in dump_paths},
            'unique_hands': len(unique_hands),
            'hero_decisions': len(targets),
            'skipped': dict(skipped),
            'target': 'realized terminal hero net return in BB, repeated at each hero decision',
            'off_policy_limitation': 'gate31400 critic scored states generated by the gate30700 official greedy policy',
        },
        'training_target_contract': {
            'reward_units': 'environment BB units at starting_stack=200',
            'gae': 'gamma=0.999 lambda=0.95, returns=advantages+old_values',
            'value_target_clip': 'per trajectory [-hero_chips,+villain_chips]',
            'loss': 'MSE with coefficient 0.5 inside Trinal-Clip PPO',
            'logged_value_loss_limitation': 'aggregate MSE alone does not expose scale, EV, or calibration',
        },
        'global': global_metrics,
        'strata': strata,
        'decision': decision,
        'claim_scope': 'reporting-only route diagnostic; not Slumbot strength evidence',
    }
    out_json = Path(args.out_json); out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    lines = [
        '# VALUE-AUDIT-001', '',
        f"- Decision: `{decision['decision']}`",
        f"- Route-pivot EXP-W1 eligible: `{decision['route_pivot_exp_w1_eligible']}`",
        f"- EXP-W1 registration authorized now: `{decision['exp_w1_registration_authorized_now']}`",
        f"- Checkpoint: `{payload['checkpoint']['iteration']} / {payload['checkpoint']['hands']}`",
        f"- Dataset: `{len(dump_paths)}` files, `{len(unique_hands)}` hands, `{len(targets)}` hero decisions",
        f"- Target mean/std BB: `{global_metrics.get('target_mean_bb'):.4f}` / `{global_metrics.get('target_std_bb'):.4f}`",
        f"- Prediction mean/std BB: `{global_metrics.get('prediction_mean_bb'):.4f}` / `{global_metrics.get('prediction_std_bb'):.4f}`",
        f"- Explained variance: `{global_metrics.get('explained_variance')}`",
        f"- RMSE / target std: `{global_metrics.get('rmse_over_target_std')}`",
        f"- Calibration slope/intercept: `{global_metrics.get('calibration_slope')}` / `{global_metrics.get('calibration_intercept_bb')}`",
        f"- Red flags: `{decision['global_red_flags']}`; supporting strata `{decision['supporting_strata_count']}`",
        '', '## Stratified metrics', '',
        '| stratum | n | EV | RMSE/std | slope | bias BB |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for key, metric in sorted(strata.items()):
        lines.append(
            f"| {key} | {metric.get('n')} | {metric.get('explained_variance')} | "
            f"{metric.get('rmse_over_target_std')} | {metric.get('calibration_slope')} | {metric.get('bias_bb')} |"
        )
    lines += [
        '', '## Limits', '',
        '- This is a reporting-only, off-policy calibration audit. It does not measure poker strength.',
        '- Terminal outcomes contain substantial irreducible card/runout variance; low positive EV alone is not classified as a critic failure.',
        '- EXP-W1 is authorized only by the explicit multi-signal decision rule in the JSON artifact.',
        '',
    ]
    out_md.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'decision': decision, 'global': global_metrics, 'decisions': len(targets)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
