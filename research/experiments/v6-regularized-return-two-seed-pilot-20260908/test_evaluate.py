"""Synthetic evaluator-review tests: zero poker environment executions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import evaluate as ev


class ReviewTests(unittest.TestCase):
    def test_interval(self):
        self.assertEqual(ev.interval([1,1,1])['ci95'],[100,100])
        self.assertAlmostEqual(ev.interval([-1,0,1])['bb100'],0)

    def test_keys(self):
        keys=set(); decks=set()
        for stage in (1,2):
            for seed in ('1','3'):
                for anchor in ('standard10','cfr4'):
                    for _,key,deck in ev.deals(stage,seed,anchor):
                        self.assertNotIn(key,keys); keys.add(key)
                        self.assertNotIn(tuple(deck),decks); decks.add(tuple(deck))
                        self.assertEqual(set(deck),set(range(52)))

    def test_full_review_and_mutations(self):
        with tempfile.TemporaryDirectory(prefix='regularized-eval-review-') as folder:
            root=Path(folder)
            anchors={f'anchor{i}':{} for i in range(8)}
            contract=dict(hashes={},policies={'1':{},'3':{}},anchors=anchors)
            ev.write(root/'stage1_evaluation_contract.json',contract)
            raw=root/'stage1_evaluation_hands.jsonl'
            first_rows=[]
            with raw.open('w') as h:
                for seed in contract['policies']:
                    for anchor in anchors:
                        for index,key,deck in ev.deals(1,seed,anchor):
                            for label,reward in [('parent',0),('control',1),('regularized',3)]:
                                for seat in (0,1):
                                    row=dict(seed=seed,anchor=anchor,index=index,key=key,deck=deck,
                                        policy=label,seat=seat,reward_bb=reward,decisions=2)
                                    if len(first_rows)<2: first_rows.append(row)
                                    h.write(json.dumps(row)+'\n')
            terminal=root/'stage1_evaluation_terminal.json'
            ev.write(terminal,dict(raw_sha=ev.sha(raw)))
            with patch.object(ev,'BASE',root): ev.review(1)
            result=ev.read(root/'stage1_evaluation_review.json')
            self.assertTrue(result['passed']); self.assertEqual(result['hands'],49152)
            for seed in ('1','3'):
                report=result['reports'][seed]['regularized_minus_control']
                self.assertEqual(report['pooled']['ci95'],[200,200])
                self.assertEqual(report['pooled']['paired_decks'],4096)
                self.assertEqual(report['transfer']['paired_decks'],2048)
            # Recompute terminal digest deliberately: rejection must come from
            # semantic/order validation, not just a stale raw checksum.
            cases=[]
            for field,value in [('seat',1),('key',-1),('reward_bb',201),('reward_bb',float('nan')),
                                ('decisions',0),('policy','regularized'),('deck',list(range(52)))]:
                bad=copy.deepcopy(first_rows[0]); bad[field]=value; cases.append([bad])
            cases.append([first_rows[0],first_rows[0]])
            for rows in cases:
                with self.subTest(rows=rows):
                    raw.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                    terminal.write_text(json.dumps(dict(raw_sha=ev.sha(raw))))
                    with patch.object(ev,'BASE',root),self.assertRaises((AssertionError,StopIteration)):
                        ev.review(1)
            terminal.write_text(json.dumps(dict(raw_sha='wrong')))
            with patch.object(ev,'BASE',root),self.assertRaises(AssertionError): ev.review(1)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    ev.write(Path(__file__).with_name('evaluator_test_result.json'),dict(tests=result.testsRun,
        passed=result.wasSuccessful(),failures=len(result.failures),errors=len(result.errors),
        environment_hands=0,synthetic_rows=49152))
    raise SystemExit(0 if result.wasSuccessful() else 1)
