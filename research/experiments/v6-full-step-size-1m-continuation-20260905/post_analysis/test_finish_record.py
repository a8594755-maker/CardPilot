"""Synthetic decision and bounded-mutation tests; no logger or poker execution."""
import subprocess

import pytest

from finish_record import mutation_batches, validate_decision


def decision():
    return {'post_terminal_review_sha256': 'a' * 64, 'curve_comparison_sha256': 'b' * 64,
            'goal_achieved': False, 'summary': 'Measured evidence', 'conclusion': 'Uncertain',
            'decision': 'Research choice', 'next_step': 'Specific next action'}


def test_complete_decision():
    validate_decision(decision(), 'a' * 64, 'b' * 64)


@pytest.mark.parametrize('key', ['post_terminal_review_sha256', 'curve_comparison_sha256'])
def test_wrong_evidence_binding(key):
    row = decision()
    row[key] = 'c' * 64
    with pytest.raises(ValueError, match='bound'):
        validate_decision(row, 'a' * 64, 'b' * 64)


@pytest.mark.parametrize('key', ['summary', 'conclusion', 'decision', 'next_step'])
def test_missing_research_field(key):
    row = decision()
    row[key] = ' '
    with pytest.raises(ValueError, match='missing research'):
        validate_decision(row, 'a' * 64, 'b' * 64)


def test_internal_cannot_qualify_goal():
    row = decision()
    row['goal_achieved'] = True
    with pytest.raises(ValueError, match='cannot qualify'):
        validate_decision(row, 'a' * 64, 'b' * 64)


def test_batched_mutations_preserve_all_pairs_and_order():
    prefix = ['python', 'logger.py', 'update', 'same-record']
    entries = [('--artifact', 'C:/directory with spaces/' + str(i) + '.json') for i in range(30)]
    batches = list(mutation_batches(prefix, entries, max_chars=230))
    assert 1 < len(batches) < len(entries)
    assert all(batch[:len(prefix)] == prefix and len(subprocess.list2cmdline(batch)) < 230 for batch in batches)
    assert [x for batch in batches for x in batch[len(prefix):]] == [x for pair in entries for x in pair]


def test_empty_mutations_do_not_invoke_logger():
    assert list(mutation_batches(['python', 'logger.py'], [])) == []


def test_oversize_single_mutation_rejected():
    with pytest.raises(ValueError, match='command-line limit'):
        list(mutation_batches(['python', 'logger.py'], [('--artifact', 'x' * 1000)], max_chars=200))
