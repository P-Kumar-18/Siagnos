"""Regression: existing chapter-event rules ("Chapter consumption rules remain unchanged").

Bucket 1: destination <= chapters_read -> confirmed immediately.
Bucket 2: destination == chapter_number + 1 -> the chapter being left is credited.
Bucket 3: anything else -> unresolved, nothing written until confirmed.

Bucket 1 is evaluated before bucket 2 (spec lists it first; the implementation
does the same). Nothing here depends on sessions or ratings.
"""
import random
from datetime import timedelta

import pytest

from tests.tracker.helpers import (
    T0,
    behaviour_state,
    close,
    progress,
    read_through,
    seed_fic,
)

pytestmark = pytest.mark.integration


# ---- Bucket 2: clean N+1 progression ---------------------------------------

def test_clean_progress_credits_the_chapter_being_left(cur):
    fic = seed_fic(cur, 1001)
    result = progress(cur, fic, chapter=1, destination=2, at=T0)

    assert result["written"] is True
    state = behaviour_state(cur, 1001)
    assert state["chapters_read"] == 1  # chapter 1 credited, not the destination
    assert state["closed_at"] == T0
    assert state["return_visits"] == 0


def test_sequential_reading_1_to_5(cur):
    fic = seed_fic(cur, 1002)
    last = read_through(cur, fic, upto=4)  # leaves 1,2,3,4 via Next

    state = behaviour_state(cur, 1002)
    assert state["chapters_read"] == 4
    assert state["return_visits"] == 0
    assert state["closed_at"] == last


# ---- Bucket 1: destination <= chapters_read --------------------------------

def test_previous_chapter_navigation_is_confirmed_and_changes_nothing_else(cur):
    fic = seed_fic(cur, 1003)
    last = read_through(cur, fic, upto=5)
    at = last + timedelta(minutes=2)

    result = progress(cur, fic, chapter=6, destination=5, at=at)  # AO3 "Previous Chapter"

    assert result["written"] is True
    state = behaviour_state(cur, 1003)
    assert state["chapters_read"] == 5
    assert state["closed_at"] == at


def test_destination_at_or_below_chapters_read_is_confirmed(cur):
    fic = seed_fic(cur, 1004)
    last = read_through(cur, fic, upto=8)
    at = last + timedelta(minutes=2)

    result = progress(cur, fic, chapter=2, destination=6, at=at)  # chapter-index jump to known chapter

    assert result["written"] is True
    state = behaviour_state(cur, 1004)
    assert state["chapters_read"] == 8
    assert state["closed_at"] == at


def test_bucket_1_takes_precedence_over_bucket_2(cur):
    """chapters_read=10, leave 4 -> 5. Destination 5 is both <= max and == chapter+1.

    Bucket 1 wins, so nothing new is credited and chapters_read stays 10.
    """
    fic = seed_fic(cur, 1005, current_chapters=20)
    last = read_through(cur, fic, upto=10)

    progress(cur, fic, chapter=4, destination=5, at=last + timedelta(minutes=1))

    assert behaviour_state(cur, 1005)["chapters_read"] == 10


# ---- Bucket 3: unresolved ---------------------------------------------------

def test_unresolved_jump_on_a_new_fic_writes_nothing(cur):
    fic = seed_fic(cur, 1006)
    result = progress(cur, fic, chapter=2, destination=10, at=T0)  # skips ahead

    assert result["written"] is False
    assert behaviour_state(cur, 1006) is None


def test_unresolved_jump_leaves_existing_state_untouched(cur):
    fic = seed_fic(cur, 1007)
    last = read_through(cur, fic, upto=3)
    before = behaviour_state(cur, 1007)

    result = progress(cur, fic, chapter=4, destination=12, at=last + timedelta(minutes=5))

    assert result["written"] is False
    assert behaviour_state(cur, 1007) == before


def test_unresolved_close_credits_nothing_and_sets_no_closed_at(cur):
    fic = seed_fic(cur, 1008)
    result = close(cur, fic, chapter=4, at=T0)  # tab closed on a never-credited chapter

    assert result["written"] is False
    assert behaviour_state(cur, 1008) is None  # no row, so no closed_at either


def test_unresolved_close_beyond_credited_progress_changes_nothing(cur):
    fic = seed_fic(cur, 1009)
    last = read_through(cur, fic, upto=3)
    before = behaviour_state(cur, 1009)

    result = close(cur, fic, chapter=6, at=last + timedelta(hours=1))

    assert result["written"] is False
    assert behaviour_state(cur, 1009) == before


# ---- Confirmation of unresolved events -------------------------------------

def test_confirmation_credits_chapter_with_the_original_timestamp(cur):
    fic = seed_fic(cur, 1010)
    original_close = T0
    close(cur, fic, chapter=2, at=original_close)  # unresolved, nothing written
    assert behaviour_state(cur, 1010) is None

    # Days later the prompt is answered yes; the client sends the ORIGINAL time.
    result = close(cur, fic, chapter=2, at=original_close, confirmation=True)

    assert result["written"] is True
    state = behaviour_state(cur, 1010)
    assert state["chapters_read"] == 2
    assert state["closed_at"] == original_close


def test_confirmation_never_lowers_chapters_read(cur):
    fic = seed_fic(cur, 1011)
    last = read_through(cur, fic, upto=7)

    close(cur, fic, chapter=3, at=last + timedelta(minutes=1), confirmation=True)

    assert behaviour_state(cur, 1011)["chapters_read"] == 7


def test_confirmation_credits_a_one_shot(cur):
    """A one-shot has no N+1, so a close is its only exit and stays unresolved.

    Only the confirmation path can credit it. (The extension cannot send a
    confirmation yet; see the blocked-items report.)
    """
    fic = seed_fic(cur, 1012, current_chapters=1, total_chapters=1, status="completed")
    assert close(cur, fic, chapter=1, at=T0)["written"] is False

    close(cur, fic, chapter=1, at=T0, confirmation=True)

    assert behaviour_state(cur, 1012)["chapters_read"] == 1


# ---- chapters_read never decreases -----------------------------------------

def test_chapters_read_is_monotonic_over_a_random_event_stream(cur):
    rng = random.Random(20261006)
    fic = seed_fic(cur, 1013, current_chapters=30)
    at = T0
    previous = 0

    for _ in range(300):
        at += timedelta(minutes=rng.randint(1, 600))
        chapter = rng.randint(1, 30)
        kind = rng.choice(["next", "prev", "jump", "close", "confirm"])
        if kind == "next":
            progress(cur, fic, chapter, chapter + 1, at)
        elif kind == "prev":
            progress(cur, fic, chapter, max(1, chapter - 1), at)
        elif kind == "jump":
            progress(cur, fic, chapter, rng.randint(1, 30), at)
        elif kind == "close":
            close(cur, fic, chapter, at)
        else:
            close(cur, fic, chapter, at, confirmation=True)

        state = behaviour_state(cur, 1013)
        current = state["chapters_read"] if state else 0
        assert current >= previous, f"chapters_read dropped {previous} -> {current}"
        previous = current


def test_rereading_an_early_chapter_after_reaching_a_later_one_keeps_the_max(cur):
    fic = seed_fic(cur, 1014, current_chapters=12)
    last = read_through(cur, fic, upto=10)
    progress(cur, fic, chapter=4, destination=3, at=last + timedelta(minutes=1))

    assert behaviour_state(cur, 1014)["chapters_read"] == 10
