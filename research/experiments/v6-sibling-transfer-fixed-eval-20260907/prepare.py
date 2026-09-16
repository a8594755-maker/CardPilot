"""Fixed source/deck/forward preflight without completing hands."""
import random
import sys
import torch
import run_eval as t
def main():
    torch.set_num_threads(1)
    q=t.read(t.BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    t.require(q['passed'],'panel')
    anchors={'standard10':str(t.ROOT/'models/baseline/standard10/latest.pt')}
    anchors.update({k:q['candidates'][k]['path'] for k in ('moving_s1','moving_s3','half_lr_s1','half_lr_s3')})
    inputs={}; paths=set(anchors.values())
    reviewed=t.read(t.TRIAL/'post_terminal_review.json')
    t.require(reviewed['passed'],'unreviewed trial')
    expected={anchors['standard10']:'91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'}
    for seed,arm in t.ORDER:
        endpoint=str(t.TRIAL/f'seed{seed}_{arm}_stage2/latest.pt')
        paths.add(endpoint); expected[endpoint]=reviewed['input_sha256'][endpoint]
        binding=t.read(t.TRIAL/f'seed{seed}_{arm}_stage1/parent_contract.json')
        paths.add(binding['path']); expected[binding['path']]=binding['sha256']
    sys.path.insert(0,str(t.ROOT/'scripts'))
    from alpha_holdem.v5_mirror_eval import init_model,read_checkpoint
    from alpha_holdem.v6_elo_eval import greedy_action
    from alpha_holdem.rules_v6 import ChipState
    for path in paths:
        p=t.Path(path); inputs[path]=t.sha(p)
        if path in expected: t.require(inputs[path]==expected[path],'endpoint/reference changed')
        if path in [c['path'] for c in q['candidates'].values()]:
            t.require(inputs[path]==next(c['sha256'] for c in q['candidates'].values() if c['path']==path),'candidate changed')
        model=init_model(read_checkpoint(p),'cuda').eval()
        for i in range(16):
            deck=list(range(52)); random.Random(810000+i).shuffle(deck)
            greedy_action(model,ChipState.new(deck),observation_style='legacy_v4',device='cuda')
        del model
    decks=[]
    for seed in (1,3):
        for index in range(5):
            rng=random.Random(20265901+10*seed+1000003*index)
            for _ in range(1024):
                deck=list(range(52)); rng.shuffle(deck); decks.append({'deck':deck})
    t.require(len({tuple(r['deck']) for r in decks})==10240,'repeated deck')
    corpus={str(p):t.sha(p) for p in (t.ROOT/'research/experiments').rglob('common_deck_pairs.jsonl.gz')}
    freshness=t.old.ctl.evidence.check_prior_decks(decks,corpus)
    for p in (t.ROOT/'scripts/alpha_holdem').rglob('*.py'): inputs[str(p)]=t.sha(p)
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            p=t.Path(file).resolve()
            if p.is_relative_to(t.ROOT) and p.suffix=='.py' and p.is_file(): inputs[str(p)]=t.sha(p)
    inputs[str(t.BASE/'protocol.md')]=t.sha(t.BASE/'protocol.md')
    inputs[str(t.BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')]=t.sha(t.BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    t.ex.check_hashes(inputs)
    t.write_new(t.BASE/'preflight.json',{'passed':True,'anchors':anchors,'input_sha256':inputs,'prior_corpus':corpus,
        'freshness':freshness,'forward_root_states_per_model':16,'models':len(paths),'evaluation_hands':0,
        'scope':'Legal finite greedy forwards on16 synthetic root states per model; reused evaluator for later streets, not full runtime parity proof.'})
    print('Preflight passed; no completed poker hands.')
if __name__=='__main__': main()
