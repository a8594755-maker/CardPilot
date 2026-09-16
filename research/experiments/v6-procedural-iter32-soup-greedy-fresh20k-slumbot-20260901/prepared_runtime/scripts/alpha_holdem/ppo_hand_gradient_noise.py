"""Opt-in, fixed-weight actor-gradient probes clustered by complete poker hands.

The caller supplies lengths from train_v5.split_complete_hand_blocks; a marked
trajectory and its optional second self-play trajectory are never split.
No backward(), optimizer mutation, or process-global RNG draw occurs here.
"""
import hashlib
import json
import math

import numpy as np
import torch
from torch.distributions import Categorical


def hand_group_indices(hand_lengths, num_groups, rows, seed=20260897):
    lengths = [int(value) for value in hand_lengths]
    if (num_groups < 2 or len(lengths) < num_groups or any(v <= 0 for v in lengths)
            or sum(lengths) != rows or any(v != original for v, original in zip(lengths, hand_lengths))):
        raise ValueError('Need complete positive hand lengths and at least two equal-hand groups')
    per_group = len(lengths)//num_groups
    order = np.random.default_rng(seed).permutation(len(lengths)).tolist()
    used = per_group*num_groups
    starts = np.cumsum([0, *lengths]).tolist()
    hand_groups = [order[i*per_group:(i+1)*per_group] for i in range(num_groups)]
    row_groups = [[row for hand in hands for row in range(starts[hand], starts[hand+1])]
                  for hands in hand_groups]
    metadata = dict(seed=seed, input_hands=len(lengths), used_hands=used,
                    hands_per_group=per_group, group_hand_indices=hand_groups,
                    excluded_remainder_hand_indices=order[used:],
                    hand_lengths=lengths, group_transition_rows=list(map(len, row_groups)),
                    used_transition_rows=sum(map(len, row_groups)))
    metadata['sha256'] = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    return row_groups, metadata


def summarize_gram(gram, hands_per_group):
    """Sufficient statistics of K equal-hand gradient estimates, in float64."""
    gram = torch.as_tensor(gram, dtype=torch.float64, device='cpu')
    k = len(gram)
    if k < 2 or gram.shape != (k, k) or not torch.isfinite(gram).all():
        raise ValueError('Invalid gradient Gram matrix')
    if not torch.allclose(gram, gram.T, rtol=1e-10, atol=1e-12):
        raise ValueError('Gradient Gram matrix must be symmetric')
    mean_squared = float(gram.mean())
    raw_variance = float((gram.diag().sum()-k*gram.mean())/(k-1))
    if raw_variance < -1e-10:
        raise ValueError('Inconsistent negative gradient covariance')
    variance = max(0., raw_variance)
    signal = mean_squared-variance/k
    resolved = signal > 1e-20
    noise_ratio = variance/signal if resolved else None
    cosines = []
    for i in range(k):
        for j in range(i+1, k):
            denominator = math.sqrt(max(0., float(gram[i, i]*gram[j, j])))
            if denominator > 1e-20:
                cosines.append(float(gram[i, j])/denominator)
    return dict(gram=gram.tolist(), groups=k, mean_gradient_squared_norm=mean_squared,
                group_covariance_trace=variance, estimated_signal_squared_norm=signal,
                signal_resolved=resolved, noise_to_signal_at_group_size=noise_ratio,
                simple_noise_scale_hands=(hands_per_group*noise_ratio if resolved else None),
                pairwise_cosine_mean=(sum(cosines)/len(cosines) if cosines else None),
                pairwise_positive_dot_fraction=(sum(v > 0 for v in cosines)/len(cosines) if cosines else None),
                noisy_or_unresolved=(noise_ratio > 1 if resolved else variance > 1e-20))


def hand_gradient_noise(model, reference_policy, *, cards, actions, extras, masks,
                        selected_actions, old_log_probs, advantages, hand_lengths,
                        num_groups, eps, delta1, reference_kl_coef, entropy_coef,
                        entropy_floor):
    params = [(name, p) for name, p in model.named_parameters() if p.requires_grad]
    actor = [(name, p) for name, p in params
             if name.startswith(('policy_head.', 'preflop_policy_head.'))]
    if not actor or any(not name.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.'))
                        for name, _ in params):
        raise ValueError('Hand-gradient probe requires frozen representation and native trainable policy heads')
    for net in [model, reference_policy]:
        if net is None:
            continue
        if any(isinstance(module, torch.nn.modules.batchnorm._BatchNorm)
               or (isinstance(module, torch.nn.modules.dropout._DropoutNd) and module.p > 0)
               for module in net.modules()):
            raise ValueError('Probe cannot mutate running statistics or consume dropout randomness')
    row_groups, grouping = hand_group_indices(hand_lengths, num_groups, len(cards))
    # Common denominator preserves the transition-weighted objective, even when
    # equal numbers of hands have different trajectory lengths across groups.
    denominator = grouping['used_transition_rows']/num_groups
    parameters = [p for _, p in actor]
    vectors = {key: [] for key in ['ppo', 'source_kl', 'entropy']}
    weighted_entropies = []
    for rows in row_groups:
        idx = torch.tensor(rows, dtype=torch.long, device=cards.device)
        logits, _ = model(cards[idx], actions[idx], extras[idx], masks[idx])
        probs = logits.float().softmax(-1)
        dist = Categorical(probs)
        logp = dist.log_prob(selected_actions[idx])
        ratio = (logp-old_log_probs[idx]).exp()
        adv = advantages[idx]
        capped = torch.where(adv < 0, ratio.clamp(max=delta1), ratio)
        ppo = -torch.minimum(capped*adv, ratio.clamp(1-eps, 1+eps)*adv).sum()/denominator
        entropy = dist.entropy().sum()/denominator
        weighted_entropies.append(float(entropy.detach()))
        kl = logits.sum()*0.
        if reference_policy is not None and reference_kl_coef > 0:
            with torch.no_grad():
                ref_logits, _ = reference_policy(cards[idx], actions[idx], extras[idx], masks[idx])
                q = ref_logits.float().softmax(-1)
            kl = reference_kl_coef*(q*(q.clamp_min(1e-8).log()-probs.clamp_min(1e-8).log())).sum()/denominator
        for name, loss in [('ppo', ppo), ('source_kl', kl), ('entropy', entropy)]:
            grads = torch.autograd.grad(loss, parameters, retain_graph=True, allow_unused=True)
            vectors[name].append(torch.cat([(torch.zeros_like(p) if g is None else g).detach().flatten().cpu().double()
                                            for p, g in zip(parameters, grads)]))
    entropy_mean = sum(weighted_entropies)/num_groups
    effective_entropy_coef = entropy_coef*(5. if entropy_mean < entropy_floor else 1.)
    matrices = {name: torch.stack(value) for name, value in vectors.items()}
    matrices['actor'] = matrices['ppo']+matrices['source_kl']-effective_entropy_coef*matrices['entropy']
    slices, offset = {'all_actor': list(range(matrices['ppo'].shape[1]))}, 0
    for name, parameter in actor:
        group = name.split('.')[0]
        slices.setdefault(group, []).extend(range(offset, offset+parameter.numel()))
        offset += parameter.numel()
    summaries = {}
    for group, indices in slices.items():
        summaries[group] = {}
        for component, matrix in matrices.items():
            local = matrix[:, indices]
            summaries[group][component] = summarize_gram(local@local.T, grouping['hands_per_group'])
    return dict(schema='cardpilot.whole_hand_gradient_noise.v1', grouping=grouping,
                parameter_names=[name for name, _ in actor], actor_parameter_count=offset,
                entropy_mean=entropy_mean, effective_entropy_coef=effective_entropy_coef,
                groups=summaries, scope='fixed_preupdate_weights_unpreconditioned_actor_gradients',
                caveat='Descriptive simple noise scale, not an optimal batch estimate or poker-strength claim. '
                       'Whole hands clustered, but full-batch advantage normalization and adaptive league induce dependencies. '
                       'Entropy boost is fixed at selected full-batch mean for all diagnostic groups; actual PPO is unchanged.')
