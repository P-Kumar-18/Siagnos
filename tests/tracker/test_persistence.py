"""Rule 22: PostgreSQL is the persistence layer. State must live in the database, not the process.

"API restart" = re-import routes from scratch and use brand-new connections between requests,
so nothing in memory can carry state across. Episode state is exercised through the real
HTTP route with the real process_tracking_event.

Not covered here (no implementation to test): browser/service-worker restart persistence of
the client-side pending-close timestamp. The extension keeps no pending state; see the report.
"""
from datetime import timedelta

import pytest

from tests.tracker.helpers import (
    DAY,
    HOUR,
    T0,
    behaviour_state,
    episodes,
    progress,
    read_through,
    seed_fic,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def api(cur, connect, load_routes):
    """Return build(): a FRESH app (fresh module import, fresh connections) per call."""

    def build():
        return load_routes(
            resolve=lambda payload: {"fic_id": payload["fic_id"]},
            ingest=lambda payload: {"error": "unused"},
            get_connection=connect,
        )[1]

    return build


def post_progress(client, fic_id, chapter, destination, at):
    return _post(client, {
        "fic_id": fic_id, "chapter_number": chapter, "event_type": "progress",
        "destination_chapter": destination, "timestamp": at.isoformat() + "Z",
    })


def post_close(client, fic_id, chapter, at, confirmation=False):
    return _post(client, {
        "fic_id": fic_id, "chapter_number": chapter, "event_type": "close",
        "timestamp": at.isoformat() + "Z", "is_confirmation": confirmation,
    })


def _post(client, body):
    response = client.post("/tracker/event", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_aggregate_state_and_open_episode_survive_a_new_connection(cur, connect):
    fic = seed_fic(cur, 7001)
    last = read_through(cur, fic, upto=4)
    at = last + 2 * DAY
    progress(cur, fic, chapter=2, destination=3, at=at)

    fresh = connect().cursor()
    state = behaviour_state(fresh, 7001)
    assert state["chapters_read"] == 4
    assert state["return_visits"] == 0                  # the episode has not resolved yet
    assert state["closed_at"] == at
    (ep,) = episodes(fresh, 7001)
    assert ep["status"] == "in_progress" and ep["previous_max_chapter"] == 4


def test_episode_lifecycle_across_api_restarts(cur, connect, api):
    seed_fic(cur, 7002, current_chapters=20)
    at = T0
    app = api()
    for chapter in range(1, 5):
        at = T0 + timedelta(minutes=chapter)
        post_progress(app, 7002, chapter, chapter + 1, at)

    start = at + 5 * DAY
    post_progress(api(), 7002, 2, 3, start)                       # restart 1: episode begins
    post_progress(api(), 7002, 3, 4, start + HOUR)                # restart 2: same episode extended
    fresh = connect().cursor()
    assert [e["status"] for e in episodes(fresh, 7002)] == ["in_progress"]
    assert episodes(fresh, 7002)[0]["revisited_chapters"] == [3, 4]

    result = post_progress(api(), 7002, 2, 3, start + HOUR + 3 * DAY)   # restart 3: >= 24h boundary
    assert result["return_visit_recorded"] is True

    fresh = connect().cursor()
    assert [e["status"] for e in episodes(fresh, 7002)] == ["resolved_return", "in_progress"]
    assert behaviour_state(fresh, 7002)["return_visits"] == 1


def test_provisional_reread_survives_restart_and_continuation_still_wins(cur, connect, api):
    seed_fic(cur, 7003, current_chapters=30)
    last = read_through(cur, seed_fic_ref(cur, 7003), upto=10)
    at = last + 31 * DAY
    for chapter in (1, 2, 3, 4):                                  # threshold for 10 is 4
        post_close(api(), 7003, chapter, at)                      # a new "process" for every event

    ep = episodes(connect().cursor(), 7003)[0]
    assert ep["status"] == "in_progress" and ep["revisited_chapters"] == [1, 2, 3, 4]

    post_progress(api(), 7003, 10, 11, at + HOUR)                 # restart, then keep reading
    post_progress(api(), 7003, 11, 12, at + 2 * HOUR)             # confirms 11, above the old max
    post_close(api(), 7003, 1, at + 2 * HOUR + 2 * DAY)           # boundary: resolves

    fresh = connect().cursor()
    assert episodes(fresh, 7003)[0]["status"] == "resolved_continuation"
    state = behaviour_state(fresh, 7003)
    assert state["chapters_read"] == 11 and state["return_visits"] == 1


def test_chapters_read_does_not_regress_across_restarts(cur, connect, api):
    seed_fic(cur, 7004, current_chapters=20)
    at = T0
    for chapter in range(1, 9):
        at = T0 + timedelta(minutes=chapter)
        post_progress(api(), 7004, chapter, chapter + 1, at)
    post_progress(api(), 7004, 3, 2, at + timedelta(minutes=1))   # restart, then go backwards
    assert behaviour_state(connect().cursor(), 7004)["chapters_read"] == 8


def seed_fic_ref(cur, fic_id):
    """Fic row already inserted by the caller; return the helper object without re-inserting."""
    from tests.tracker.helpers import Fic
    return Fic(fic_id, 30, None, "on_going")
