"""On-policy zero-sum trajectory reward transform, not a complete R-NaD trainer.

Inputs describe every player's chronological action in a completed hand. Actor
log probabilities must be of the frozen rollout policy, not epsilon-mixture
behavior or a retrospectively refit model. No importance correction is provided.
"""
import math


def transformed_returns(actors, log_policy, log_reference, terminal_bb, eta_bb):
    if len(actors)!=len(log_policy) or len(actors)!=len(log_reference):
        raise ValueError('unaligned chronological actions')
    if len(terminal_bb)!=2 or not all(math.isfinite(x) for x in terminal_bb):
        raise ValueError('invalid terminal payoffs')
    if abs(sum(terminal_bb))>1e-9 or not math.isfinite(eta_bb) or eta_bb<0:
        raise ValueError('zero-sum payoffs and nonnegative finite eta required')
    rewards=[]
    for player,lp,lr in zip(actors,log_policy,log_reference):
        if player not in (0,1) or not all(math.isfinite(x) and x<=0 for x in (lp,lr)):
            raise ValueError('invalid actor or log probability')
        cost=eta_bb*(lp-lr)
        signed=[cost,cost]; signed[player]=-cost
        rewards.append(tuple(signed))
    running=list(terminal_bb); returns=[]
    for reward in reversed(rewards):
        running=[running[s]+reward[s] for s in (0,1)]
        returns.append(tuple(running))
    returns.reverse()
    return dict(shaping_rewards_bb=rewards,returns_bb=returns,
                terminal_bb=tuple(terminal_bb),eta_bb=eta_bb)
