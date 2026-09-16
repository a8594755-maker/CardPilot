"""Offline qualification only; defer all logger writes until the owner exits."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[2]
PRIOR=ROOT/'research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis'


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def main():
    output=HERE/'qualification.json'
    assert not output.exists(), 'preserve prior qualification'
    sources=[HERE/n for n in ('review.py','test_review.py','curve_comparison.py','test_curve_comparison.py','qualify_review.py')]
    sources += [PRIOR/'review.py',PRIOR/'curve_comparison.py']
    hashes={str(path):sha(path) for path in sources}
    current_tree=ast.parse((HERE/'review.py').read_text(encoding='utf-8'))
    prior_tree=ast.parse((PRIOR/'review.py').read_text(encoding='utf-8'))
    functions=lambda tree:{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    current,previous=functions(current_tree),functions(prior_tree)
    reused=('severe','counter_deltas','adam_steps')
    assert all(current[name]==previous[name] for name in reused)
    started=time.monotonic()
    suites=[]
    for test,xml in [('test_review.py','review_tests.xml'),('test_curve_comparison.py','curve_tests.xml')]:
        path=HERE/xml
        assert not path.exists(), 'preserve prior test output'
        argv=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',str(HERE/test),f'--junitxml={path}']
        process=subprocess.run(argv,cwd=HERE,capture_output=True,text=True,encoding='utf-8',timeout=45)
        parsed=list(ET.parse(path).getroot().iter('testsuite')) if path.exists() else []
        counts={k:sum(int(s.get(k,'0')) for s in parsed) for k in ('tests','failures','errors','skipped')}
        suites.append({'command':argv,'cwd':str(HERE),'exit_code':process.returncode,
                       'counts':counts,'stdout':process.stdout,'stderr':process.stderr,
                       'xml_path':str(path),'xml_sha256':sha(path) if path.exists() else None})
    passed=all(s['exit_code']==0 and s['counts']['tests']>0 and
               not any(s['counts'][k] for k in ('failures','errors','skipped')) for s in suites)
    assert all(sha(path)==digest for path,digest in hashes.items()), 'qualification source changed'
    result={'passed':passed,'created_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
            'wall_seconds':time.monotonic()-started,'source_sha256':hashes,'suites':suites,
            'unchanged_AST_functions':reused,'changed_scope':'parents/counters, arm labels, fresh eval seeds, fixed equal LR, independent gradient-route/origin checks',
            'new_poker_hands':0,'current_outcomes_read':False,'logger_writes':0,
            'terminal_review_executed':False,'goal_achieved':False}
    with output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps({'passed':passed,'tests':sum(s['counts']['tests'] for s in suites),
                      'counts':[s['counts'] for s in suites],'new_hands':0}))
    raise SystemExit(0 if passed else 1)


if __name__=='__main__':
    main()
