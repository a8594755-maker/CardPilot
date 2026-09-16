"""Synthetic decision-binding tests; no logger, processes, models or poker."""
import pytest

from finish_record import validate_decision


def decision():
    return {'post_terminal_review_sha256': 'a' * 64, 'goal_achieved': False,
            'summary': 'Measured result', 'conclusion': 'Uncertain strength',
            'decision': 'Research choice', 'next_step': 'Specific next experiment'}


def test_complete_decision_is_admitted():
    validate_decision(decision(), 'a' * 64)


def test_wrong_report_rejected():
    with pytest.raises(ValueError, match='bound'):
        validate_decision(decision(), 'b' * 64)


@pytest.mark.parametrize('field', ['summary', 'conclusion', 'decision', 'next_step'])
def test_missing_research_field_rejected(field):
    row = decision()
    row[field] = ' '
    with pytest.raises(ValueError, match='missing research'):
        validate_decision(row, 'a' * 64)


def test_internal_goal_claim_rejected():
    row = decision()
    row['goal_achieved'] = True
    with pytest.raises(ValueError, match='cannot qualify'):
        validate_decision(row, 'a' * 64)
