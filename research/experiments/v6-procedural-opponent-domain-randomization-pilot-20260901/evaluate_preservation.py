from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from alpha_holdem.execution_v6 import load_policy, sha256_file  # noqa: E402
from alpha_holdem.policy_contract_v6 import from_external, observation  # noqa: E402


CORPUS = (
    ROOT
    / 'research'
    / 'experiments'
    / 'v6-actor-raw-greedy-fresh5k-slumbot-20260901'
)
EXPECTED_PARENT_SHA256 = (
    '9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4'
)


def probabilities(model, observations, device: str, batch_size: int = 512):
    output = []
    with torch.no_grad():
        for start in range(0, len(observations), batch_size):
            batch = observations[start:start + batch_size]
            tensors = [
                torch.as_tensor(
                    np.stack([row[key] for row in batch]),
                    dtype=torch.float32,
                    device=device,
                )
                for key in ('card_info', 'action_info', 'extra_info', 'legal_mask')
            ]
            logits, _ = model(*tensors)
            vectors = logits.detach().cpu().numpy().astype(np.float64)
            for vector, row in zip(vectors, batch):
                legal = np.flatnonzero(row['legal_mask'])
                if not np.isfinite(vector[legal]).all():
                    raise ValueError('non-finite legal policy logit')
                weights = np.exp(vector[legal] - np.max(vector[legal]))
                result = np.zeros(9, dtype=np.float64)
                result[legal] = weights / weights.sum()
                output.append(result)
    return np.asarray(output)


def comparison(endpoint_probs, parent_probs):
    tv = 0.5 * np.abs(endpoint_probs - parent_probs).sum(axis=1)
    disagreement = (
        np.argmax(endpoint_probs, axis=1) != np.argmax(parent_probs, axis=1)
    )
    return tv, disagreement


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--control', required=True)
    parser.add_argument('--treatment', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()

    corpus_record = json.loads(
        (CORPUS / 'experiment.json').read_text(encoding='utf-8-sig')
    )
    corpus_review = json.loads(
        (CORPUS / 'reviewed_analysis.json').read_text(encoding='utf-8-sig')
    )
    corpus_audit = json.loads(
        (CORPUS / 'combined_audit.json').read_text(encoding='utf-8-sig')
    )
    if corpus_record['status'] != 'COMPLETED':
        raise ValueError('parent state corpus experiment is not complete')
    if corpus_review['status'] != 'PASS' or corpus_audit['status'] != 'PASS':
        raise ValueError('parent state corpus evidence did not pass review')

    observations = []
    metadata = []
    input_hands = []
    for session in range(1, 9):
        path = CORPUS / 'sessions' / f's{session:02d}' / 'hands.jsonl'
        input_hands.append({
            'path': str(path.relative_to(ROOT)),
            'sha256': sha256_file(path),
        })
        for hand_line, line in enumerate(
            path.read_text(encoding='utf-8').splitlines(), 1
        ):
            hand = json.loads(line)
            if hand['successful_hand'] != hand_line:
                raise ValueError('non-contiguous corpus hand index')
            if hand['model_sha256'] != EXPECTED_PARENT_SHA256:
                raise ValueError('corpus model identity mismatch')
            for decision_index, decision in enumerate(hand['decisions']):
                response = decision['response']
                state = from_external(
                    response['action'],
                    response['hole_cards'],
                    response.get('board', []),
                    response['client_pos'],
                )
                obs, _ = observation(state, include_position=False)
                if decision['legal_mask'] != obs['legal_mask'].tolist():
                    raise ValueError('corpus legal mask replay mismatch')
                observations.append(obs)
                metadata.append({
                    'session': session,
                    'hand': hand_line,
                    'decision': decision_index,
                    'street': int(state.street),
                    'seat': int(response['client_pos']),
                })

    parent, _, parent_sha = load_policy(args.parent, args.device)
    control, _, control_sha = load_policy(args.control, args.device)
    treatment, _, treatment_sha = load_policy(args.treatment, args.device)
    if parent_sha != EXPECTED_PARENT_SHA256:
        raise ValueError('unexpected parent checkpoint SHA256')
    parent_probs = probabilities(parent, observations, args.device)
    control_probs = probabilities(control, observations, args.device)
    treatment_probs = probabilities(treatment, observations, args.device)
    control_tv, control_disagreement = comparison(control_probs, parent_probs)
    treatment_tv, treatment_disagreement = comparison(
        treatment_probs, parent_probs
    )

    metrics_path = output / 'state_metrics.jsonl'
    with metrics_path.open('x', encoding='utf-8', newline='\n') as handle:
        for meta, c_tv, c_dis, t_tv, t_dis in zip(
            metadata,
            control_tv,
            control_disagreement,
            treatment_tv,
            treatment_disagreement,
        ):
            handle.write(json.dumps({
                **meta,
                'control_total_variation': float(c_tv),
                'control_greedy_disagreement': int(c_dis),
                'treatment_total_variation': float(t_tv),
                'treatment_greedy_disagreement': int(t_dis),
            }, separators=(',', ':')) + '\n')

    for path, expected in (
        (args.parent, parent_sha),
        (args.control, control_sha),
        (args.treatment, treatment_sha),
    ):
        if sha256_file(path) != expected:
            raise RuntimeError(f'frozen checkpoint changed during replay: {path}')
    treatment_mean_tv = float(np.mean(treatment_tv))
    treatment_disagreement_rate = float(np.mean(treatment_disagreement))
    gate = {
        'mean_total_variation_at_most_0_02': treatment_mean_tv <= 0.02,
        'greedy_disagreement_at_most_0_02': (
            treatment_disagreement_rate <= 0.02
        ),
    }
    gate['passed'] = all(gate.values())
    summary = {
        'schema': 'cardpilot.parent_state_preservation.v1',
        'status': 'COMPLETED',
        'states': len(observations),
        'policy_queries': 3 * len(observations),
        'parent_sha256': parent_sha,
        'control_sha256': control_sha,
        'treatment_sha256': treatment_sha,
        'control_mean_total_variation': float(np.mean(control_tv)),
        'control_greedy_disagreement_rate': float(
            np.mean(control_disagreement)
        ),
        'treatment_mean_total_variation': treatment_mean_tv,
        'treatment_greedy_disagreement_rate': treatment_disagreement_rate,
        'gate': gate,
        'input_hands': input_hands,
        'state_metrics_sha256': sha256_file(metrics_path),
        'wall_time_seconds': time.time() - started,
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    (output / 'summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
