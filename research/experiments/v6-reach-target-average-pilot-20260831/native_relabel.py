"""Streaming native-only reach targets with preserved per-block probability evidence."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from reach_targets import relabel_hand,reservoir_index

KEYS=('card_info','action_info','extra_info','legal_mask')

def chunks(path,size=1024):
    rows=[]
    with Path(path).open() as handle:
        for line in handle:
            if not line.endswith('\n'):raise ValueError('Partial native raw line')
            rows.append((json.loads(line),line))
            if len(rows)==size:
                yield rows
                rows=[]
    if rows:yield rows

def reconstruct(rows,expected_start,retained=None,reservoir=None):
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import observation,apply_incr
    from temporal_average import observation_digest
    arrays={k:[] for k in KEYS}
    actors,slots,teachers,known,hashes,lengths,hand_ids=[],[],[],[],[],[],[]
    retained_matches=[]
    qualification_states=[]
    for hand,(row,_) in enumerate(rows,expected_start):
        assert row['index']==hand
        state=ChipState.new(row['deck'])
        lengths.append(len(row['events']))
        assert lengths[-1]>0
        for decision,event in enumerate(row['events']):
            obs,table=observation(state)
            assert event['seat']==state.actor and event['teacher']==row['teachers'][state.actor]
            assert table[event['action']]==event['increment']
            digest=observation_digest(obs)
            assert digest==event['observation_sha256']
            local=len(actors)
            for key in KEYS:arrays[key].append(obs[key])
            actors.append(state.actor);slots.append(event['action']);teachers.append(event['teacher'])
            known.append(event['probabilities']);hashes.append(digest);hand_ids.append(hand)
            if retained is not None:
                position=retained.get((hand,decision))
                if position is not None:
                    for key in KEYS:assert np.array_equal(obs[key],reservoir['arrays'][key][position])
                    retained_matches.append((local,position))
            if expected_start==0 and len(qualification_states)<64:
                qualification_states.append(copy.deepcopy(state))
            state=apply_incr(state,event['increment'])
        assert state.terminal
    return dict(arrays={k:np.stack(v) for k,v in arrays.items()},actors=np.asarray(actors,dtype=np.int64),
        slots=np.asarray(slots,dtype=np.int64),known_teachers=np.asarray(teachers,dtype=np.int64),
        known_probs=np.asarray(known,dtype=np.float64),observation_sha256=np.asarray(hashes,dtype='S64'),
        lengths=np.asarray(lengths,dtype=np.int64),hand_ids=np.asarray(hand_ids,dtype=np.int64),
        retained_matches=retained_matches,qualification_states=qualification_states)

def targets_for_block(probs,lengths,actors,slots):
    targets=[]
    offset=0
    for length in lengths:
        n=int(length)
        target,_=relabel_hand(probs[:,offset:offset+n],actors[offset:offset+n],slots[offset:offset+n])
        targets.append(target);offset+=n
    if offset!=probs.shape[1]:raise ValueError('Hand offsets do not cover all probabilities')
    return np.concatenate(targets)

def stream_relabel(source,out_dir,expected_hands,expected_decisions,infer,save_json,sha,progress,
                   reservoir=None,validation=False):
    source,out_dir=Path(source),Path(out_dir)
    if out_dir.exists():raise ValueError('No relabel overwrite/restart')
    out_dir.mkdir()
    retained=reservoir_index(reservoir['ids']) if reservoir is not None else None
    output=np.full((len(retained),9),np.nan) if retained is not None else None
    seen=np.zeros(len(retained),dtype=bool) if retained is not None else None
    records=[]
    validation_arrays={key:[] for key in KEYS}
    all_targets,all_hands,all_actors=[],[],[]
    qualification_states=[]
    completed,decisions,max_delta=0,0,0.
    for block,rows in enumerate(chunks(source)):
        parsed=reconstruct(rows,completed,retained,reservoir)
        if not qualification_states:qualification_states=parsed['qualification_states']
        probabilities=np.asarray(infer(parsed['arrays']))
        count=len(parsed['actors'])
        assert probabilities.shape==(3,count,9) and np.isfinite(probabilities).all()
        assert np.all(probabilities[:,parsed['arrays']['legal_mask']==0]==0)
        actual=probabilities[parsed['known_teachers'],np.arange(count)]
        delta=float(np.abs(actual-parsed['known_probs']).max())
        assert delta<=1e-4
        max_delta=max(max_delta,delta)
        targets=targets_for_block(probabilities,parsed['lengths'],parsed['actors'],parsed['slots'])
        if retained is not None:
            for local,position in parsed['retained_matches']:
                assert not seen[position]
                output[position]=targets[local]
                seen[position]=True
        if validation:
            for key in KEYS:validation_arrays[key].append(parsed['arrays'][key])
            all_targets.append(targets);all_hands.append(parsed['hand_ids']);all_actors.append(parsed['actors'])
        path=out_dir/f'block{block:04d}.npz'
        np.savez_compressed(path,teacher_probabilities=probabilities,targets=targets,
            lengths=parsed['lengths'],actors=parsed['actors'],slots=parsed['slots'],
            hand_ids=parsed['hand_ids'],observation_sha256=parsed['observation_sha256'],
            legal_mask=parsed['arrays']['legal_mask'].astype(np.uint8))
        row=dict(block=block,first_hand=completed,hands=len(rows),decisions=count,
            normalized_lines_sha256=hashlib.sha256(''.join(line for _,line in rows).encode()).hexdigest(),
            path=str(path),sha256=sha(path),actual_teacher_max_delta=delta,
            retained_rows=len(parsed['retained_matches']))
        records.append(row)
        completed+=len(rows);decisions+=count
        save_json(out_dir/'block_manifest.json',records)
        progress(completed,decisions,int(seen.sum()) if seen is not None else 0)
    assert completed==expected_hands
    if expected_decisions is not None:assert decisions==expected_decisions
    if seen is not None:assert seen.all() and np.isfinite(output).all()
    result=dict(status='PASS',hands=completed,decisions=decisions,blocks=len(records),
        retained_rows=0 if seen is None else len(seen),actual_teacher_max_delta=max_delta,
        source_sha256=sha(source),block_manifest_sha256=sha(out_dir/'block_manifest.json'))
    if output is not None:
        np.save(out_dir/'reach_targets.npy',output)
        np.save(out_dir/'retained_ids.npy',reservoir['ids'])
        result.update(reach_targets_sha256=sha(out_dir/'reach_targets.npy'),retained_ids_sha256=sha(out_dir/'retained_ids.npy'))
    bundle=None
    if validation:
        bundle=dict(arrays={k:np.concatenate(v) for k,v in validation_arrays.items()},
            targets=np.concatenate(all_targets),hands=np.concatenate(all_hands),actors=np.concatenate(all_actors))
        np.savez_compressed(out_dir/'validation_arrays.npz',**bundle['arrays'])
        np.save(out_dir/'validation_targets.npy',bundle['targets'])
        np.savez_compressed(out_dir/'validation_metadata.npz',hands=bundle['hands'],actors=bundle['actors'])
    save_json(out_dir/'relabel_analysis.json',result)
    return result,output,bundle,qualification_states
