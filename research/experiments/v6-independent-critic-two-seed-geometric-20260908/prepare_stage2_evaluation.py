"""Prepare isolated second-dose evaluation; never launch or change live inputs."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'unexpected source boundary: {old}')
    return source.replace(old, new)


def build_runner(source):
    source = source.replace('stage1', 'stage2')
    source = once(source, "    terminal = read(BASE/'stage2_training_terminal.json')",
        "    previous = read(BASE/'stage1_raw_review.json')\n"
        "    assert previous['passed_evidence_checks'] and previous['decision'] == 'CONTINUE_PREREGISTERED_1M_DOSE'\n"
        "    assert previous['evaluation_hands'] == 131072\n"
        "    terminal = read(BASE/'stage2_training_terminal.json')")
    source = once(source, "f'{seed}_1'", "f'{seed}_2'")
    source = once(source, "count = completed + 4*completed_raw_rows", "count = 131072 + completed + 4*completed_raw_rows")
    source = once(source, "f'evaluation_hands={completed}'", "f'evaluation_hands={131072+completed}'")
    return source


def build_reviewer(source):
    source = source.replace('stage1', 'stage2')
    source = once(source, "f'{seed}_1'", "f'{seed}_2'")
    source = once(source, "'stage':1", "'stage':2")
    source = once(source, "'CONTINUE_PREREGISTERED_1M_DOSE'", "'FIXED_DOSE_COMPLETE_RESEARCH_DECISION_REQUIRED'")
    source = once(source, "    unique = set()", """    unique = set()
    previous = read(BASE/'stage1_raw_review.json')
    assert previous['passed_evidence_checks']
    prior_decks = set()
    for name, digest in previous['raw_hashes'].items():
        assert sha(Path(name)) == digest
        with gzip.open(name, 'rt', encoding='utf-8') as handle:
            prior_decks.update(tuple(json.loads(line)['deck']) for line in handle)
    assert len(prior_decks) == 16384""")
    source = once(source, "                    assert deck not in unique",
        "                    assert deck not in unique and deck not in prior_decks")
    return source


def main():
    outputs = {}
    for original, target, transform in (
        ('run_evaluation.py', 'run_stage2_evaluation.py', build_runner),
        ('review_evaluation.py', 'review_stage2_evaluation.py', build_reviewer),
    ):
        source = (BASE/original).read_text(encoding='utf-8')
        candidate = transform(source)
        compile(candidate, str(BASE/target), 'exec')
        outputs[target] = candidate
    # Fail before writing anything if either destination exists.
    assert all(not (BASE/name).exists() for name in outputs)
    for name, candidate in outputs.items():
        with (BASE/name).open('x', encoding='utf-8') as handle:
            handle.write(candidate)
    print(json.dumps({'status':'PREPARED_NOT_LAUNCHED', 'sha256':{
        name:hashlib.sha256((BASE/name).read_bytes()).hexdigest() for name in outputs}}))


if __name__ == '__main__':
    main()
