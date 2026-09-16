"""Independent postprocessing of frozen cell statistics, not an evaluator."""
import math


def moments(values):
    if len(values) < 2 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 200 for x in values):
        raise ValueError('Invalid raw seat/pair observations')
    mean = math.fsum(values)/len(values)
    std = math.sqrt(math.fsum((x-mean)**2 for x in values)/(len(values)-1))
    return mean, std, 1.96*std/math.sqrt(len(values))


def equal_number(actual, expected):
    if type(actual) not in (int, float) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError('Stored statistic disagrees with independent raw arithmetic')


def count(actual, expected=None):
    if type(actual) is not int or actual < 0 or (expected is not None and actual != expected):
        raise ValueError('Invalid or inconsistent count')


def review_cell(doc):
    """Recompute descriptive statistics and OOD validity, without changing gates.

    OOD counts are aggregated evidence, not per-action traces. Their consistency
    is checked here; correctness of observation construction still relies on the
    captured and tested evaluator implementation.
    """
    threshold = .15  # The frozen evaluator's preregistered CLI default.
    equal_number(doc['gate']['anchor_ood_valid_threshold'], threshold)
    valid = []
    summaries = []
    for row in doc['anchors']:
        outcomes = row['paired_outcomes']
        pairs, bb, sb = [outcomes[k] for k in ['overall_bb_per_hand', 'bb_bb_per_hand', 'sb_bb_per_hand']]
        if len(bb) != len(sb) or len(pairs) != len(bb):
            raise ValueError('Unpaired seat arrays')
        count(row['pairs'], len(pairs))
        count(row['hands'], 2*len(pairs))
        for x, y, z in zip(pairs, bb, sb):
            equal_number(x, (y+z)/2)
        mean, std, half = moments(pairs)
        equal_number(row['candidate_bb100'], mean*100)
        equal_number(row['candidate_std_bb_per_hand_pair_mean'], std)
        equal_number(row['candidate_ci95_bb100'], half*100)
        hands = [*bb, *sb]
        unpaired_mean, _, unpaired_half = moments(hands)
        equal_number(row['unpaired_hand_bb100'], unpaired_mean*100)
        equal_number(row['unpaired_hand_ci95_bb100'], unpaired_half*100)
        equal_number(row['total_candidate_bb'], math.fsum(hands))
        for seat, values in [('bb', bb), ('sb', sb)]:
            seat_row = row['candidate_by_seat'][seat]
            seat_mean, seat_std, seat_half = moments(values)
            count(seat_row['hands'], len(values))
            for key, expected in dict(candidate_bb100=seat_mean*100,
                candidate_ci95_bb100=seat_half*100, candidate_std_bb_per_hand=seat_std,
                total_candidate_bb=math.fsum(values)).items():
                equal_number(seat_row[key], expected)
        for prefix, values in [('pair', [x+y for x, y in zip(bb, sb)]), ('hand', hands)]:
            wins, losses = sum(x > .01 for x in values), sum(x < -.01 for x in values)
            for name, expected in [('wins', wins), ('losses', losses), ('draws', len(values)-wins-losses)]:
                count(row[f'{prefix}_{name}'], expected)
        for who in ['candidate', 'anchor']:
            decisions, ood = row['policy_decisions'][who], row['ood_nodes'][who]
            count(decisions)
            count(ood)
            if ood > decisions:
                raise ValueError('More OOD nodes than policy decisions')
            equal_number(row[f'{who}_ood_node_rate'], ood/max(decisions, 1))
        count(row['decisions'], sum(row['policy_decisions'].values()))
        equal_number(row['anchor_ood_valid_threshold'], threshold)
        is_valid = row['ood_nodes']['anchor']/max(row['policy_decisions']['anchor'], 1) <= threshold
        for key in ['anchor_ood_valid', 'mirror_signal_valid']:
            if type(row[key]) is not bool or row[key] != is_valid:
                raise ValueError('Stored OOD validity disagrees with counts')
        valid.append(is_valid)
        summaries.append(dict(anchor=row['anchor'], pairs=len(pairs), hands=len(hands),
            candidate_bb100=mean*100, candidate_ci95_bb100=half*100, anchor_ood_valid=is_valid))
    if type(doc['gate']['all_anchors_pass_ood_gate']) is not bool or doc['gate']['all_anchors_pass_ood_gate'] != all(valid):
        raise ValueError('Aggregate OOD validity disagrees with cells')
    return summaries
