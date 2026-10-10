"""Rules 12 to 16: which chapter a confirmed event credits, and what unresolved events may touch.

  Bucket 1  destination <= chapters_read  -> the DESTINATION is revisited, previously consumed content
  Bucket 2  destination == chapter + 1    -> the chapter being LEFT is confirmed, never the destination
  Bucket 3  anything else                 -> unresolved: must not mutate behaviour OR return_episodes
  close / confirmation                    -> confirms chapter_number
  Navigating to a chapter never, by itself, makes that chapter consumed (rule 15).
"""
import copy

import pytest

from tests.tracker.helpers import (
    BUG1,
    DAY,
    HOUR,
    behaviour_state,
    close,
    episodes,
    progress,
    read_through,
    resolve_by_new_boundary,
    seed_fic,
    statuses,
)

pytestmark = pytest.mark.integration


def history_of_four(cur, fic_id):
    fic = seed_fic(cur, fic_id, current_chapters=20)
    last = read_through(cur, fic, upto=4)   # previous maximum = 4
    return fic, last


# ---- rule 15: a destination is not consumed ---------------------------------

def test_navigating_to_the_next_chapter_does_not_consume_it(cur):
    fic, last = history_of_four(cur, 6101)
    at = last + 5 * DAY

    progress(cur, fic, chapter=4, destination=5, at=at)    # leave 4 for 5

    assert behaviour_state(cur, 6101)["chapters_read"] == 4   # 5 is NOT credited by arriving
    (ep,) = episodes(cur, 6101)
    assert ep["current_max_chapter"] == 4
    resolve_by_new_boundary(cur, fic, at)
    assert statuses(cur, 6101)[0] == "resolved_return"        # arriving at 5 is not continuation


def test_leaving_the_new_chapter_is_what_consumes_it(cur):
    fic, last = history_of_four(cur, 6102)
    at = last + 5 * DAY
    progress(cur, fic, chapter=4, destination=5, at=at)
    progress(cur, fic, chapter=5, destination=6, at=at + HOUR)   # now 5 is left: confirmed

    assert behaviour_state(cur, 6102)["chapters_read"] == 5
    assert episodes(cur, 6102)[0]["current_max_chapter"] == 5
    resolve_by_new_boundary(cur, fic, at + HOUR)
    assert statuses(cur, 6102)[0] == "resolved_continuation"


def test_a_forward_jump_does_not_consume_its_destination(cur):
    fic, last = history_of_four(cur, 6103)
    at = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=at)       # starts the episode (revisit)
    result = progress(cur, fic, chapter=3, destination=12, at=at + HOUR)  # index jump into new territory

    assert result["written"] is False
    assert behaviour_state(cur, 6103)["chapters_read"] == 4
    ep = episodes(cur, 6103)[0]
    assert ep["current_max_chapter"] <= ep["previous_max_chapter"]   # destination 12 not credited
    resolve_by_new_boundary(cur, fic, at)
    assert statuses(cur, 6103)[0] == "resolved_return"


# ---- rule 12: unresolved events mutate nothing ------------------------------

def snapshot(cur, fic_id):
    return copy.deepcopy((behaviour_state(cur, fic_id), episodes(cur, fic_id)))


@pytest.mark.parametrize(
    "send",
    [
        pytest.param(lambda cur, fic, at: progress(cur, fic, chapter=2, destination=9, at=at), id="jump-past-N+1"),
        pytest.param(lambda cur, fic, at: close(cur, fic, chapter=7, at=at), id="close-on-unconsumed-chapter"),
    ],
)
def test_unresolved_event_does_not_start_an_episode(cur, send):
    fic, last = history_of_four(cur, 6110)
    before = snapshot(cur, 6110)

    result = send(cur, fic, last + 5 * DAY)       # >= 24h later, but unresolved

    assert result["written"] is False
    assert result["return_visit_recorded"] is False
    assert snapshot(cur, 6110) == before
    assert episodes(cur, 6110) == []


@pytest.mark.parametrize(
    "send",
    [
        pytest.param(lambda cur, fic, at: progress(cur, fic, chapter=2, destination=9, at=at), id="jump-past-N+1"),
        pytest.param(lambda cur, fic, at: close(cur, fic, chapter=7, at=at), id="close-on-unconsumed-chapter"),
    ],
)
@pytest.mark.parametrize("delay", [HOUR, 10 * DAY], ids=["within-24h", "after-24h"])
def test_unresolved_event_does_not_extend_or_resolve_an_active_episode(cur, send, delay):
    fic, last = history_of_four(cur, 6111)
    start = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=start)
    before = snapshot(cur, 6111)

    result = send(cur, fic, start + delay)

    assert result["written"] is False
    assert snapshot(cur, 6111) == before            # last_activity_at, revisits, status all untouched
    assert behaviour_state(cur, 6111)["return_visits"] == 0


# ---- bucket 1 / 2: which chapter is credited as revisited -------------------

def test_bucket_1_backward_navigation_revisits_the_destination(cur):
    fic, last = history_of_four(cur, 6120)
    progress(cur, fic, chapter=3, destination=2, at=last + 5 * DAY)         # "Previous Chapter"
    assert episodes(cur, 6120)[0]["revisited_chapters"] == [2]


def test_bucket_1_index_jump_revisits_the_destination_not_the_origin(cur):
    fic, last = history_of_four(cur, 6121)
    progress(cur, fic, chapter=1, destination=4, at=last + 5 * DAY)
    assert episodes(cur, 6121)[0]["revisited_chapters"] == [4]


def test_bucket_2_inside_old_territory_confirms_the_chapter_being_left(cur):
    fic, last = history_of_four(cur, 6122)
    progress(cur, fic, chapter=4, destination=5, at=last + 5 * DAY)         # leave the old maximum
    assert episodes(cur, 6122)[0]["revisited_chapters"] == [4]


def test_explicit_close_confirms_chapter_number(cur):
    fic, last = history_of_four(cur, 6123)
    close(cur, fic, chapter=3, at=last + 5 * DAY)
    assert episodes(cur, 6123)[0]["revisited_chapters"] == [3]


def test_backward_navigation_never_lowers_chapters_read_or_the_episode_maximum(cur):
    fic, last = history_of_four(cur, 6124)
    at = last + 5 * DAY
    progress(cur, fic, chapter=4, destination=5, at=at)
    progress(cur, fic, chapter=5, destination=4, at=at + HOUR)
    assert behaviour_state(cur, 6124)["chapters_read"] == 4
    assert episodes(cur, 6124)[0]["current_max_chapter"] >= 4


# ---- backward navigation AFTER progressing inside the episode ---------------
# chapters_read has now moved above the episode's previous_max_chapter. A destination in
# (previous_max, chapters_read] is "previously consumed" under rule 13 (it is <= chapters_read).

@pytest.mark.spec_mismatch
@pytest.mark.xfail(strict=True, reason=BUG1)
def test_previous_chapter_after_consuming_new_chapters_is_confirmed(cur):
    fic, last = history_of_four(cur, 6130)
    at = last + 5 * DAY
    progress(cur, fic, chapter=5, destination=6, at=at)           # consumes 5; chapters_read = 5
    result = progress(cur, fic, chapter=6, destination=5, at=at + HOUR)   # "Previous Chapter" back to 5

    assert result["written"] is True
    assert behaviour_state(cur, 6130)["chapters_read"] == 5
    assert statuses(cur, 6130) == ["in_progress"]


@pytest.mark.spec_mismatch
@pytest.mark.xfail(strict=True, reason=BUG1)
def test_index_jump_back_into_chapters_consumed_this_episode_is_confirmed(cur):
    fic, last = history_of_four(cur, 6131)
    at = last + 5 * DAY
    for chapter in range(5, 9):                                    # consumes 5..8; chapters_read = 8
        progress(cur, fic, chapter=chapter, destination=chapter + 1, at=at + chapter * HOUR)
    assert behaviour_state(cur, 6131)["chapters_read"] == 8

    result = progress(cur, fic, chapter=9, destination=6, at=at + 10 * HOUR)   # jump back to 6

    assert result["written"] is True
    assert behaviour_state(cur, 6131)["chapters_read"] == 8
