"""Rule 10 and 11: reread threshold = min(ceil(previous_max_chapter * 0.40), 15).

Pure unit tests of src.tracker.logic.reread_threshold (no database).
"""
import pytest

from src.tracker.logic import (
    REREAD_CHAPTER_CAP,
    REREAD_FRACTION,
    REREAD_MINIMUM_INTERVAL,
    RETURN_INACTIVITY_THRESHOLD,
    reread_threshold,
)
from datetime import timedelta

SPEC_TABLE = {1: 1, 2: 1, 3: 2, 5: 2, 10: 4, 20: 8, 30: 12, 40: 15, 50: 15, 100: 15}


def exact(n):
    """Reference in integer arithmetic: ceil(2n/5) capped at 15."""
    return min(-(-2 * n // 5), 15)


def test_constants_match_the_specification():
    assert RETURN_INACTIVITY_THRESHOLD == timedelta(hours=24)
    assert REREAD_MINIMUM_INTERVAL == timedelta(days=30)
    assert REREAD_FRACTION == 0.40
    assert REREAD_CHAPTER_CAP == 15


@pytest.mark.parametrize("n,expected", sorted(SPEC_TABLE.items()))
def test_specification_table(n, expected):
    assert reread_threshold(n) == expected


@pytest.mark.parametrize("n,expected", [(4, 2), (6, 3), (7, 3), (8, 4), (9, 4), (11, 5), (14, 6), (16, 7)])
def test_fractional_values_round_up(n, expected):
    assert reread_threshold(n) == expected


@pytest.mark.parametrize("n,expected", [(35, 14), (36, 15), (37, 15), (38, 15), (39, 15)])
def test_cap_engages_exactly_where_forty_percent_exceeds_fifteen(n, expected):
    assert reread_threshold(n) == expected


def test_cap_is_a_maximum_not_a_minimum():
    assert reread_threshold(20) == 8      # not 15
    assert reread_threshold(100) == 15


def test_no_minimum_history_requirement():
    assert reread_threshold(1) == 1       # one-shot can qualify
    assert reread_threshold(2) == 1       # two-shot can qualify


def test_float_arithmetic_never_disagrees_with_exact_arithmetic():
    for n in range(0, 20001):
        assert reread_threshold(n) == exact(n), n


def test_negative_history_is_rejected():
    with pytest.raises(ValueError):
        reread_threshold(-1)
