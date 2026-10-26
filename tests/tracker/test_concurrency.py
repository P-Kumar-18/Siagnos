"""Concurrency of two transactions touching the same fic (two tabs, or a retry racing a new event).

process_tracking_event reads the behaviour row, computes in Python, then writes ABSOLUTE
values (`return_visits = EXCLUDED.return_visits`). Without a row lock on the read, a second
transaction that read the old value can overwrite a committed increment.

Run with two real, non-autocommit connections and one thread so the interleaving is
deterministic: A resolves an episode but has not committed when B starts.
"""
import threading
import time

import psycopg
import pytest

from tests.tracker.helpers import DAY, HOUR, T0, behaviour_state, episodes, progress, read_through, seed_fic

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


def tx_connection(pg_schema):
    return psycopg.connect(
        pg_schema["dsn"], autocommit=False, options=f"-c search_path={pg_schema['schema']}"
    )


def test_a_concurrent_ordinary_event_does_not_erase_a_committed_return_visit(cur, pg_schema):
    fic = seed_fic(cur, 7101, current_chapters=20)
    last = read_through(cur, fic, upto=4)
    start = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=start)           # episode 1 in progress
    assert behaviour_state(cur, 7101)["return_visits"] == 0

    a, b = tx_connection(pg_schema), tx_connection(pg_schema)
    errors = []
    try:
        # Transaction A: this event is >= 24h after the episode's last activity, so it resolves
        # episode 1 and records the return visit. Not yet committed.
        a_result = progress(a.cursor(), fic, chapter=2, destination=3, at=start + 25 * HOUR)
        assert a_result["return_visit_recorded"] is True

        def run_b():
            try:
                # Transaction B: an ordinary event from another tab, within the episode's window.
                progress(b.cursor(), fic, chapter=2, destination=3, at=start + HOUR)
                b.commit()
            except Exception as exc:  # noqa: BLE001 - the failure mode is part of what we report
                errors.append(exc)
                b.rollback()

        worker = threading.Thread(target=run_b)
        worker.start()
        time.sleep(0.7)          # let B read the old row and block on A's locks
        a.commit()
        worker.join(15)
        assert not worker.is_alive(), "transaction B never finished"
    finally:
        a.close()
        b.close()

    state = behaviour_state(cur, 7101)
    resolved = [e for e in episodes(cur, 7101) if e["status"] != "in_progress"]
    assert len(resolved) == 1
    assert state["return_visits"] == 1, (
        f"resolved episodes={len(resolved)} but return_visits={state['return_visits']} "
        f"(B raised: {errors!r})"
    )


def test_concurrent_first_events_for_a_new_fic_leave_consistent_state(cur, pg_schema):
    """No behaviour row exists yet, so FOR UPDATE has nothing to lock and cannot serialize these.

    A (first inserter, more progress) is still uncommitted when B (a late event with LESS
    progress) reads the empty table. After both commit the row must describe the furthest
    chapter reached: chapters_read and the reading_progress derived from it must agree.
    """
    fic = seed_fic(cur, 7102, current_chapters=5, status="on_going")
    a, b = tx_connection(pg_schema), tx_connection(pg_schema)
    errors = []
    try:
        progress(a.cursor(), fic, chapter=5, destination=6, at=T0 + HOUR)    # reaches 5 of 5: up_to_date

        def run_b():
            try:
                progress(b.cursor(), fic, chapter=3, destination=4, at=T0)   # late event, reaches only 3
                b.commit()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
                b.rollback()

        worker = threading.Thread(target=run_b)
        worker.start()
        time.sleep(0.7)
        a.commit()
        worker.join(15)
        assert not worker.is_alive(), "transaction B never finished"
    finally:
        a.close()
        b.close()

    state = behaviour_state(cur, 7102)
    assert not errors, errors
    assert state["chapters_read"] == 5
    assert state["reading_progress"] == "up_to_date", state    # derived from 5, not from B's stale 3
    assert state["closed_at"] == T0 + HOUR


def test_two_concurrent_episode_resolutions_are_serialized_and_each_counted_once(cur, pg_schema):
    """Two events, each >= 24h after the previous activity, race for the same fic.

    A resolves episode 1 and starts episode 2 (uncommitted). B is a LATER event, itself >= 24h
    after A, so once it can see A's work it must resolve episode 2. Serialized correctly the fic
    ends with two resolved episodes, one in progress, and exactly two return visits. A lost update,
    a double resolution of episode 1, or an error would all break one of those.
    """
    fic = seed_fic(cur, 7103, current_chapters=20)
    last = read_through(cur, fic, upto=4)
    start = last + 5 * DAY
    progress(cur, fic, chapter=2, destination=3, at=start)                  # episode 1 in progress

    a, b = tx_connection(pg_schema), tx_connection(pg_schema)
    errors = []
    try:
        progress(a.cursor(), fic, chapter=2, destination=3, at=start + 2 * DAY)   # resolves ep 1, starts ep 2

        def run_b():
            try:
                progress(b.cursor(), fic, chapter=2, destination=3, at=start + 4 * DAY)  # resolves ep 2
                b.commit()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
                b.rollback()

        worker = threading.Thread(target=run_b)
        worker.start()
        time.sleep(0.7)
        a.commit()
        worker.join(15)
        assert not worker.is_alive(), "transaction B never finished"
    finally:
        a.close()
        b.close()

    assert not errors, errors
    assert [e["status"] for e in episodes(cur, 7103)] == ["resolved_return", "resolved_return", "in_progress"]
    assert behaviour_state(cur, 7103)["return_visits"] == 2
