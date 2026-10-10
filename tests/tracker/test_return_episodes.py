"""Stage 4 return episodes (rules 2 to 6, 20).

  * An episode BEGINS when confirmed activity occurs >= 24h after the previous confirmed
    activity on the SAME fic (inclusive).
  * It stays in_progress while activity continues (< 24h between activities).
  * It RESOLVES only when a later confirmed event is >= 24h after the episode's own last
    activity. That event belongs to the NEW episode.
  * Each resolved episode adds exactly 1 to return_visits. An in_progress episode adds 0.
  * Other fics never start, extend or resolve an episode.
"""
from datetime import timedelta

import pytest

from tests.tracker.helpers import (
    DAY,
    HOUR,
    T0,
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


def _resume(cur, fic, kind, at):
    if kind == "revisit":
        return progress(cur, fic, chapter=2, destination=3, at=at)   # bucket 1, known content
    if kind == "continuation":
        return progress(cur, fic, chapter=5, destination=6, at=at)   # bucket 2, credits chapter 5 (> max 4)
    raise ValueError(kind)


KINDS = ["revisit", "continuation"]

GAPS = [
    ("10min", timedelta(minutes=10), False),
    ("3h", 3 * HOUR, False),
    ("23h59m", 23 * HOUR + timedelta(minutes=59), False),
    ("exactly-24h", 24 * HOUR, True),
    ("24h+1s", 24 * HOUR + timedelta(seconds=1), True),
    ("5-days", 5 * DAY, True),
]


# ---- beginning an episode: 24h inclusive -----------------------------------

@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("gap_id,gap,starts", GAPS, ids=[g[0] for g in GAPS])
def test_episode_begins_at_24h_inclusive(cur, kind, gap_id, gap, starts):
    fic = seed_fic(cur, 4001)
    last = read_through(cur, fic, upto=4)

    result = _resume(cur, fic, kind, last + gap)

    assert len(episodes(cur, 4001)) == (1 if starts else 0)
    assert result["return_visit_recorded"] is False
    assert behaviour_state(cur, 4001)["return_visits"] == 0  # nothing has RESOLVED yet


def test_new_episode_records_its_starting_state(cur):
    fic = seed_fic(cur, 4002)
    last = read_through(cur, fic, upto=4)
    at = last + 5 * DAY

    progress(cur, fic, chapter=2, destination=3, at=at)

    (ep,) = episodes(cur, 4002)
    assert ep["status"] == "in_progress"
    assert ep["started_at"] == at
    assert ep["last_activity_at"] == at
    assert ep["previous_max_chapter"] == 4
    assert ep["previous_consumption_at"] == last


def test_first_ever_activity_is_never_a_return(cur):
    fic = seed_fic(cur, 4003)
    progress(cur, fic, chapter=1, destination=2, at=T0)
    assert episodes(cur, 4003) == []


# ---- staying in progress ----------------------------------------------------

def test_episode_stays_in_progress_while_activity_continues(cur):
    fic = seed_fic(cur, 4004)
    last = read_through(cur, fic, upto=4)
    at = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=at)

    for _ in range(5):  # a read every 23h for five days: never a 24h gap
        at += 23 * HOUR
        progress(cur, fic, chapter=2, destination=3, at=at)

    assert statuses(cur, 4004) == ["in_progress"]
    assert behaviour_state(cur, 4004)["return_visits"] == 0
    assert episodes(cur, 4004)[0]["last_activity_at"] == at


# ---- resolving an episode: 24h from the episode's own last activity ---------

def test_episode_resolves_exactly_24h_after_its_last_activity(cur):
    fic = seed_fic(cur, 4005)
    last = read_through(cur, fic, upto=4)
    start = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=start)
    activity = start + 10 * HOUR
    progress(cur, fic, chapter=2, destination=3, at=activity)  # extends the episode

    just_before = activity + 23 * HOUR + timedelta(minutes=59)
    progress(cur, fic, chapter=2, destination=3, at=just_before)
    assert statuses(cur, 4005) == ["in_progress"]
    assert behaviour_state(cur, 4005)["return_visits"] == 0

    boundary = just_before + 24 * HOUR  # measured from the LAST activity, not the start
    result = progress(cur, fic, chapter=2, destination=3, at=boundary)

    assert statuses(cur, 4005) == ["resolved_return", "in_progress"]
    assert result["return_visit_recorded"] is True
    assert result["resolved_episode_status"] == "resolved_return"
    assert behaviour_state(cur, 4005)["return_visits"] == 1


def test_event_that_establishes_the_boundary_belongs_to_the_new_episode(cur):
    fic = seed_fic(cur, 4006)
    last = read_through(cur, fic, upto=4)
    first_start = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=first_start)
    old_last_activity = first_start + HOUR
    progress(cur, fic, chapter=2, destination=3, at=old_last_activity)

    boundary_at = old_last_activity + 24 * HOUR
    progress(cur, fic, chapter=2, destination=3, at=boundary_at)

    old, new = episodes(cur, 4006)
    assert old["last_activity_at"] == old_last_activity   # NOT moved to the boundary event
    assert new["started_at"] == boundary_at
    assert new["last_activity_at"] == boundary_at
    assert new["previous_max_chapter"] == 4
    assert new["previous_consumption_at"] == old_last_activity


@pytest.mark.parametrize("kind", KINDS)
def test_resolution_adds_exactly_one_return_visit(cur, kind):
    fic = seed_fic(cur, 4007)
    last = read_through(cur, fic, upto=4)
    start = last + 5 * DAY
    _resume(cur, fic, kind, start)
    # many events inside the episode must not add anything
    for minutes in (5, 10, 15, 20):
        progress(cur, fic, chapter=2, destination=3, at=start + timedelta(minutes=minutes))
    assert behaviour_state(cur, 4007)["return_visits"] == 0

    resolve_by_new_boundary(cur, fic, start + timedelta(minutes=20))
    assert behaviour_state(cur, 4007)["return_visits"] == 1

    # events inside the NEW episode still add nothing
    progress(cur, fic, chapter=2, destination=3, at=start + 2 * DAY + HOUR)
    assert behaviour_state(cur, 4007)["return_visits"] == 1


# ---- multiple episodes ------------------------------------------------------

def test_multiple_return_episodes_each_count_once_when_resolved(cur):
    fic = seed_fic(cur, 4008)
    at = read_through(cur, fic, upto=4)

    for round_number in range(1, 5):
        at += 5 * DAY                       # a >= 24h gap: begins episode number `round_number`
        progress(cur, fic, chapter=2, destination=3, at=at)
        # Episodes 1..round-1 are resolved (one visit each); the newest is still open.
        assert behaviour_state(cur, 4008)["return_visits"] == round_number - 1
        assert len(episodes(cur, 4008)) == round_number

    assert statuses(cur, 4008) == ["resolved_return"] * 3 + ["in_progress"]


def test_in_progress_episode_is_never_counted(cur):
    fic = seed_fic(cur, 4009)
    last = read_through(cur, fic, upto=4)
    progress(cur, fic, chapter=2, destination=3, at=last + 40 * DAY)

    assert statuses(cur, 4009) == ["in_progress"]
    assert behaviour_state(cur, 4009)["return_visits"] == 0


def test_no_lazy_resolution_without_a_new_event(cur):
    """Time passing is not an event: nothing resolves an episode until later confirmed activity."""
    fic = seed_fic(cur, 4010)
    last = read_through(cur, fic, upto=4)
    progress(cur, fic, chapter=2, destination=3, at=last + 40 * DAY)
    # (no further events, however long the clock runs)
    assert statuses(cur, 4010) == ["in_progress"]


# ---- cross-fic --------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_a_b_a_within_a_day_is_not_a_return(cur, kind):
    a = seed_fic(cur, 4020)
    b = seed_fic(cur, 4021)
    last_a = read_through(cur, a, upto=4)
    read_through(cur, b, upto=2, start=last_a + timedelta(minutes=10))

    _resume(cur, a, kind, last_a + HOUR)

    assert episodes(cur, 4020) == []
    assert behaviour_state(cur, 4020)["return_visits"] == 0


def test_other_fic_activity_does_not_start_extend_or_resolve_an_episode(cur):
    a = seed_fic(cur, 4022)
    b = seed_fic(cur, 4023)
    last_a = read_through(cur, a, upto=4)
    for day in range(1, 5):                                  # B read every day, A untouched
        read_through(cur, b, upto=2, start=last_a + day * DAY)
    assert episodes(cur, 4022) == []

    start = last_a + 5 * DAY                                 # A returns after its OWN 5 idle days
    progress(cur, a, chapter=2, destination=3, at=start)
    assert statuses(cur, 4022) == ["in_progress"]

    # B activity 12h later, then A again 18h after its own last activity: same episode
    read_through(cur, b, upto=2, start=start + 12 * HOUR)
    progress(cur, a, chapter=2, destination=3, at=start + 18 * HOUR)
    assert statuses(cur, 4022) == ["in_progress"]
    assert behaviour_state(cur, 4022)["return_visits"] == 0


def test_reading_b_never_creates_episodes_or_visits_for_b(cur):
    a = seed_fic(cur, 4024)
    b = seed_fic(cur, 4025)
    last_a = read_through(cur, a, upto=4)
    read_through(cur, b, upto=3, start=last_a + timedelta(minutes=10))

    assert episodes(cur, 4025) == []
    assert behaviour_state(cur, 4025)["return_visits"] == 0
