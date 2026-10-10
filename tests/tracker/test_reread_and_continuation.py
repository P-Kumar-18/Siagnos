"""Rules 7 to 11: how a return episode resolves.

Precedence: continuation > reread > ordinary return.

  resolved_continuation  the reader CONFIRMS consumption beyond previous_max_chapter
  resolved_reread        no continuation AND >= 30 days since previous_consumption_at AND
                         unique previously consumed chapter positions revisited >=
                         min(ceil(previous_max_chapter * 0.40), 15)
  resolved_return        everything else

Resolution only happens when a later confirmed event is >= 24h after the episode's last
activity (see test_return_episodes.py), so each scenario ends with `resolve_by_new_boundary`.

Revisits are made with `close` events on known chapters, all at ONE timestamp, so the
instant that age is measured at is unambiguous.
"""
from datetime import timedelta

import pytest

from src.tracker.logic import reread_threshold
from tests.tracker.helpers import (
    BUG2,
    DAY,
    HOUR,
    T0,
    behaviour_state,
    close,
    episodes,
    progress,
    read_through,
    resolve_by_new_boundary,
    revisit_closes,
    seed_fic,
    statuses,
)

pytestmark = pytest.mark.integration

_ids = iter(range(5000, 6000))


def run_episode(cur, history, revisits, gap, advance=0):
    """History of `history` chapters, then a return after `gap` that revisits chapters
    1..revisits (and optionally consumes `advance` NEW chapters), then a resolving event.
    Returns the first (now resolved) episode."""
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id, current_chapters=max(history + advance + 5, 12))
    last = read_through(cur, fic, upto=history)
    return_at = last + gap

    revisit_closes(cur, fic, list(range(1, revisits + 1)), at=return_at)
    for step in range(advance):                       # consume chapters history+1 .. history+advance
        chapter = history + 1 + step
        progress(cur, fic, chapter=chapter, destination=chapter + 1, at=return_at)
    # make sure `advance` chapters beyond the old max are CONFIRMED (leaving the last one credits it)
    resolve_by_new_boundary(cur, fic, return_at)
    return fic, episodes(cur, fic_id)[0]


# ---- reread threshold boundary, every size in the spec table ---------------

THRESHOLD_SIZES = sorted({1, 2, 3, 5, 10, 20, 30, 40, 50, 100, 6, 8, 11, 36, 37})


@pytest.mark.parametrize("history", THRESHOLD_SIZES)
def test_at_threshold_is_a_confirmed_reread(cur, history):
    threshold = reread_threshold(history)
    _, ep = run_episode(cur, history, revisits=threshold, gap=31 * DAY)
    assert ep["status"] == "resolved_reread"
    assert len(ep["revisited_chapters"]) == threshold


@pytest.mark.parametrize("history", [h for h in THRESHOLD_SIZES if reread_threshold(h) >= 2])
def test_one_below_threshold_is_only_a_return(cur, history):
    threshold = reread_threshold(history)
    _, ep = run_episode(cur, history, revisits=threshold - 1, gap=31 * DAY)
    assert ep["status"] == "resolved_return"


def test_fifteen_is_a_cap_a_hundred_chapter_history_needs_exactly_fifteen(cur):
    _, ep = run_episode(cur, 100, revisits=15, gap=31 * DAY)
    assert ep["status"] == "resolved_reread"
    _, ep = run_episode(cur, 100, revisits=14, gap=31 * DAY)
    assert ep["status"] == "resolved_return"


def test_fifteen_is_not_a_minimum_twenty_chapters_needs_eight(cur):
    _, ep = run_episode(cur, 20, revisits=8, gap=31 * DAY)
    assert ep["status"] == "resolved_reread"


def test_one_shot_reread(cur):
    fic = seed_fic(cur, 5900, current_chapters=1, total_chapters=1, status="completed")
    close(cur, fic, 1, T0, confirmation=True)           # only a confirmation can credit a one-shot
    at = T0 + 31 * DAY
    close(cur, fic, 1, at)                              # reopen and close: chapter 1 revisited
    resolve_by_new_boundary(cur, fic, at)

    (first, _) = episodes(cur, 5900)
    assert first["previous_max_chapter"] == 1
    assert first["status"] == "resolved_reread"


def test_two_shot_reread(cur):
    fic = seed_fic(cur, 5901, current_chapters=2, total_chapters=2, status="completed")
    progress(cur, fic, 1, 2, T0)
    close(cur, fic, 2, T0 + 5 * HOUR, confirmation=True)
    at = T0 + 40 * DAY
    close(cur, fic, 1, at)                              # one chapter is enough: ceil(2 * 0.4) = 1
    resolve_by_new_boundary(cur, fic, at)

    assert episodes(cur, 5901)[0]["previous_max_chapter"] == 2
    assert statuses(cur, 5901)[0] == "resolved_reread"


def test_unique_chapter_positions_count_once(cur):
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id)
    last = read_through(cur, fic, upto=10)               # threshold is 4
    at = last + 31 * DAY
    for _ in range(12):                                  # the SAME chapter, twelve times
        close(cur, fic, 1, at)
    for chapter in (2, 3):
        close(cur, fic, chapter, at)                     # three distinct chapters in total
    resolve_by_new_boundary(cur, fic, at)

    first = episodes(cur, fic_id)[0]
    assert first["revisited_chapters"] == [1, 2, 3]
    assert first["status"] == "resolved_return"


# ---- reread age: >= 30 days since previous_consumption_at ------------------
# The age is the gap between previous_consumption_at and the RETURN (the episode's
# start). All revisits share one timestamp, so the answer cannot depend on which instant
# inside the episode is used.

AGE_CASES = [
    pytest.param(30 * DAY - timedelta(minutes=1), "resolved_return", id="29d23h59m-not-eligible",
                 marks=[pytest.mark.spec_mismatch, pytest.mark.xfail(strict=True, reason=BUG2)]),
    pytest.param(30 * DAY, "resolved_reread", id="exactly-30d-eligible"),
    pytest.param(30 * DAY + timedelta(seconds=1), "resolved_reread", id="30d+1s-eligible"),
    pytest.param(29 * DAY, "resolved_return", id="29d-not-eligible",
                 marks=[pytest.mark.spec_mismatch, pytest.mark.xfail(strict=True, reason=BUG2)]),
    pytest.param(45 * DAY, "resolved_reread", id="45d-eligible"),
    pytest.param(10 * DAY, "resolved_return", id="10d-full-reread-still-only-a-return"),
]


@pytest.mark.parametrize("gap,expected", AGE_CASES)
def test_reread_age_boundary(cur, gap, expected):
    _, ep = run_episode(cur, history=10, revisits=4, gap=gap)
    assert ep["status"] == expected


@pytest.mark.spec_mismatch
@pytest.mark.xfail(strict=True, reason=BUG2)
def test_the_30_day_clock_is_measured_to_the_return_not_to_the_resolving_event(cur):
    """A full re-read 5 days after the last read is only a return, however long the reader
    stays away afterwards. (A later resolving event 60 days on must not age it.)"""
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id)
    last = read_through(cur, fic, upto=10)
    return_at = last + 5 * DAY
    revisit_closes(cur, fic, [1, 2, 3, 4, 5, 6], at=return_at)   # more than the threshold of 4
    resolve_by_new_boundary(cur, fic, return_at, gap=60 * DAY)

    assert episodes(cur, fic_id)[0]["status"] == "resolved_return"


# ---- continuation ------------------------------------------------------------

def test_return_plus_continuation(cur):
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id)
    last = read_through(cur, fic, upto=4)
    at = last + 5 * DAY
    progress(cur, fic, chapter=5, destination=6, at=at)    # confirms chapter 5, above the old max
    resolve_by_new_boundary(cur, fic, at)

    first = episodes(cur, fic_id)[0]
    assert first["status"] == "resolved_continuation"
    assert first["previous_max_chapter"] == 4 and first["current_max_chapter"] == 5
    assert behaviour_state(cur, fic_id)["chapters_read"] == 5
    assert behaviour_state(cur, fic_id)["return_visits"] == 1


def test_continuation_after_provisional_reread_wins(cur):
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id, current_chapters=20)
    last = read_through(cur, fic, upto=10)
    at = last + 31 * DAY
    revisit_closes(cur, fic, [1, 2, 3, 4], at=at)          # threshold (4) reached: provisional reread
    (ep,) = episodes(cur, fic_id)
    assert ep["status"] == "in_progress" and len(ep["revisited_chapters"]) == 4

    progress(cur, fic, chapter=10, destination=11, at=at + HOUR)   # confirms 10 (old territory)
    progress(cur, fic, chapter=11, destination=12, at=at + 2 * HOUR)  # confirms 11: beyond the old max
    resolve_by_new_boundary(cur, fic, at + 2 * HOUR)

    first = episodes(cur, fic_id)[0]
    assert first["status"] == "resolved_continuation"    # NOT resolved_reread
    assert behaviour_state(cur, fic_id)["chapters_read"] == 11
    assert behaviour_state(cur, fic_id)["return_visits"] == 1


def test_revisiting_old_chapters_before_advancing_is_continuation_not_reread(cur):
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id)
    last = read_through(cur, fic, upto=4)
    at = last + 40 * DAY                                    # old enough, and 4 >= threshold(4)=2
    for chapter in (2, 3):
        progress(cur, fic, chapter=chapter, destination=chapter + 1, at=at)
    progress(cur, fic, chapter=4, destination=5, at=at)      # confirms 4 (not yet beyond)
    progress(cur, fic, chapter=5, destination=6, at=at)      # confirms 5: beyond the old max of 4
    resolve_by_new_boundary(cur, fic, at)

    assert episodes(cur, fic_id)[0]["status"] == "resolved_continuation"


def test_threshold_reached_stays_provisional_until_a_later_boundary(cur):
    fic_id = next(_ids)
    fic = seed_fic(cur, fic_id)
    last = read_through(cur, fic, upto=10)
    at = last + 31 * DAY
    revisit_closes(cur, fic, [1, 2, 3, 4], at=at)

    # Within 24h: still the same in-progress episode, nothing resolved, no visit counted.
    close(cur, fic, 5, at + 23 * HOUR)
    assert statuses(cur, fic_id) == ["in_progress"]
    assert behaviour_state(cur, fic_id)["return_visits"] == 0

    resolve_by_new_boundary(cur, fic, at + 23 * HOUR)
    assert statuses(cur, fic_id) == ["resolved_reread", "in_progress"]
    assert behaviour_state(cur, fic_id)["return_visits"] == 1


# ---- return without reread or continuation -----------------------------------

def test_return_without_reread_or_continuation(cur):
    _, ep = run_episode(cur, history=4, revisits=2, gap=5 * DAY)
    assert ep["status"] == "resolved_return"
    assert ep["previous_max_chapter"] == 4 and ep["current_max_chapter"] <= 4
