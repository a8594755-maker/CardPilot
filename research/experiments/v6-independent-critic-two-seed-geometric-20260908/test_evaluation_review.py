import copy
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from review_evaluation import prescribed_decks


def fixture():
    rng = random.Random(123)
    rows = []
    for i in range(2):
        deck = list(range(52)); rng.shuffle(deck)
        rows.append({'anchor':'a','pair_index':i,'anchor_seed':123,'deck':deck})
    return rows


def test_exact_registered_decks():
    prescribed_decks(fixture(),['a'],123,pairs=2)


@pytest.mark.parametrize('bad',['deck','seed','duplicate','missing'])
def test_reject_wrong_evidence(bad):
    rows = fixture()
    if bad=='deck': rows[0]['deck'].reverse()
    if bad=='seed': rows[0]['anchor_seed'] += 1
    if bad=='duplicate': rows.append(copy.deepcopy(rows[0]))
    if bad=='missing': rows.pop()
    with pytest.raises(ValueError): prescribed_decks(rows,['a'],123,pairs=2)
