"""Mechanical second-dose controller; no execution until raw stage1 decision."""
from pathlib import Path
import hashlib
import json

BASE = Path(__file__).resolve().parent


def replace(text, old, new):
    if text.count(old) != 1: raise ValueError('unexpected stage1 source: '+old)
    return text.replace(old,new)


def main():
    source = BASE/'run_stage1.py'
    text = source.read_text()
    text = replace(text, "    contract = read(BASE/'input_contract.json')", """    contract = read(BASE/'input_contract.json')
    decision = read(BASE/'stage1_raw_review.json')
    assert decision['passed_evidence_checks'] and decision['decision'] == 'CONTINUE_PREREGISTERED_1M_DOSE'
    prior_stage = read(BASE/'stage1_training_terminal.json')
    stage1_hands = sum(r['new_physical_hands'] for r in prior_stage['runs'])""")
    text = replace(text, "        item = contract['parents'][str(seed)]", """        previous = BASE/f'seed{seed}_{arm}_stage1'
        evidence = read(previous/'independent_review.json')
        assert evidence['passed']
        item = {'path':str(previous/'latest.pt'),'sha256':evidence['checkpoint_sha256']}
        original_physical = read(previous/'job_contract.json')['initial_physical']""")
    text = replace(text, "        folder = BASE/f'seed{seed}_{arm}_stage1'", "        folder = BASE/f'seed{seed}_{arm}_stage2'")
    text = replace(text, "        index = argv.index('--opponent-greedy-mixture'); assert float(argv[index+1]) == 0\n        del argv[index:index+2]", """        if '--opponent-greedy-mixture' in argv:
            index = argv.index('--opponent-greedy-mixture')
            assert float(argv[index+1]) == 0
            del argv[index:index+2]""")
    text = replace(text, "'--total-environment-hands':physical+262144", "'--total-environment-hands':original_physical+1048576")
    text = replace(text, "        if arm == 'independent': argv.append('--independent-observable-critic')", "        if arm == 'independent' and '--independent-observable-critic' not in argv: argv.append('--independent-observable-critic')")
    text = replace(text, "'arm':arm,'seed':seed,'stage':1", "'arm':arm,'seed':seed,'stage':2")
    text = replace(text, "        assert actual >= 262144", "        assert actual >= original_physical+1048576-physical")
    text = replace(text, "                count = sum(r['new_physical_hands'] for r in results)", "                count = stage1_hands + sum(r['new_physical_hands'] for r in results)")
    text = replace(text, "f\"training_hands={sum(r['new_physical_hands'] for r in results)}\"", "f\"training_hands={stage1_hands+sum(r['new_physical_hands'] for r in results)}\"")
    text = text.replace("'stage1_owner.json'", "'stage2_owner.json'")
    text = text.replace("'stage1_training_terminal.json',{'status'", "'stage2_training_terminal.json',{'status'")
    text = text.replace("Stage1 training complete; stopped for fixed evaluation.", "Stage2 training complete; stopped for fixed evaluation.")
    text = text.replace("'run_stage1.py','train_job.py'", "'run_stage1.py','run_stage2.py','train_job.py'")
    compile(text,str(BASE/'run_stage2.py'),'exec')
    with (BASE/'run_stage2.py').open('x',encoding='utf-8') as handle: handle.write(text)
    print(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                      'candidate_sha256':hashlib.sha256((BASE/'run_stage2.py').read_bytes()).hexdigest(),
                      'status':'PREPARED_NOT_LAUNCHED'}))


if __name__ == '__main__': main()
