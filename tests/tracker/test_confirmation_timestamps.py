"""Rule 21: confirming an unresolved close preserves the ORIGINAL pending close timestamp.

The client sends the original time in `timestamp`. Everything derived from the confirmed
activity (closed_at, a new episode's started_at / last_activity_at) must use that time,
never the later moment the user answered the prompt.

Also: a confirmation that arrives late carries an OLD timestamp, so time-ordered state
(closed_at, an episode's last_activity_at) must never move backwards because of it.
"""
import pytest

from tests.tracker.helpers import (
    BUG3,
    DAY,
    HOUR,
    T0,
    behaviour_state,
    close,
    episodes,
    progress,
    read_through,
    seed_fic,
    statuses,
)

pytestmark = pytest.mark.integration


def test_original_timestamp_drives_closed_at_and_the_new_episode(cur):
    fic = seed_fic(cur, 6201, current_chapters=20)
    last = read_through(cur, fic, upto=4)

    pending_at = last + 2 * DAY                                   # the unresolved close
    assert close(cur, fic, chapter=5, at=pending_at)["written"] is False
    assert behaviour_state(cur, 6201)["chapters_read"] == 4 and episodes(cur, 6201) == []

    # Seven days later the user answers "yes"; the client replays the ORIGINAL timestamp.
    close(cur, fic, chapter=5, at=pending_at, confirmation=True)

    state = behaviour_state(cur, 6201)
    assert state["chapters_read"] == 5
    assert state["closed_at"] == pending_at
    (ep,) = episodes(cur, 6201)
    assert ep["started_at"] == pending_at and ep["last_activity_at"] == pending_at
    assert ep["previous_consumption_at"] == last
    assert ep["previous_max_chapter"] == 4


def test_confirmation_never_moves_closed_at_backwards(cur):
    fic = seed_fic(cur, 6202, current_chapters=20)
    last = read_through(cur, fic, upto=4)
    close(cur, fic, chapter=2, at=last + 10 * HOUR)               # later confirmed activity
    latest = behaviour_state(cur, 6202)["closed_at"]

    close(cur, fic, chapter=6, at=last + HOUR, confirmation=True) # older pending close, answered late

    assert behaviour_state(cur, 6202)["closed_at"] == latest


@pytest.mark.spec_mismatch
@pytest.mark.xfail(strict=True, reason=BUG3)
def test_late_confirmation_does_not_rewind_an_episodes_last_activity(cur):
    fic = seed_fic(cur, 6203, current_chapters=20)
    last = read_through(cur, fic, upto=4)
    old_close = last + 2 * DAY
    assert close(cur, fic, chapter=5, at=old_close)["written"] is False   # pending, unanswered

    start = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=start)                # episode begins
    close(cur, fic, chapter=5, at=old_close, confirmation=True)           # the late answer arrives now

    assert episodes(cur, 6203)[-1]["last_activity_at"] >= start           # not rewound to old_close

    progress(cur, fic, chapter=2, destination=3, at=start + HOUR)         # the reader simply keeps going
    assert statuses(cur, 6203) == ["in_progress"]                         # no false 24h boundary
    assert behaviour_state(cur, 6203)["return_visits"] == 0
