"""Rules 18 to 20, 22: the persisted shape, and that removed concepts are gone."""
import psycopg
import pytest

pytestmark = pytest.mark.integration


def columns(cur, table):
    cur.execute(
        """
        SELECT column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (table,),
    )
    return {name: (dtype, udt, nullable) for name, dtype, udt, nullable in cur.fetchall()}


def test_behaviour_table_has_exactly_the_specified_columns(cur):
    cols = columns(cur, "behaviour")
    assert set(cols) == {"fic_id", "chapters_read", "return_visits", "reading_progress", "closed_at"}
    assert cols["fic_id"][0] == "bigint"
    assert cols["chapters_read"][0] == "integer" and cols["chapters_read"][2] == "NO"
    assert cols["return_visits"][0] == "integer" and cols["return_visits"][2] == "NO"
    assert cols["reading_progress"][1] == "reading_status" and cols["reading_progress"][2] == "NO"
    assert cols["closed_at"][0] == "timestamp without time zone" and cols["closed_at"][2] == "YES"


def test_return_episodes_table_has_exactly_the_specified_columns(cur):
    cols = columns(cur, "return_episodes")
    assert set(cols) == {
        "episode_id", "fic_id", "started_at", "last_activity_at", "previous_max_chapter",
        "previous_consumption_at", "revisited_chapters", "current_max_chapter", "status",
    }
    assert all(nullable == "NO" for _, _, nullable in cols.values())
    assert cols["revisited_chapters"][1] == "_int4"          # integer[]
    assert cols["status"][1] == "episode_status"
    for ts in ("started_at", "last_activity_at", "previous_consumption_at"):
        assert cols[ts][0] == "timestamp without time zone"


def test_episode_status_enum_values(cur):
    cur.execute(
        """
        SELECT e.enumlabel FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'episode_status' AND n.nspname = current_schema()
        ORDER BY e.enumsortorder
        """
    )
    assert [r[0] for r in cur.fetchall()] == [
        "in_progress", "resolved_return", "resolved_continuation", "resolved_reread",
    ]


def test_ratings_are_gone_from_the_database(cur):
    cur.execute(
        """
        SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'rating_types' AND n.nspname = current_schema()
        """
    )
    assert cur.fetchone()[0] == 0
    assert "ratings" not in columns(cur, "behaviour")


def test_removed_concepts_are_absent_from_the_python_layer():
    from src.tracker import logic
    from src.tracker.models import TrackingEvent

    assert "rating" not in TrackingEvent.model_fields
    for legacy in ("is_new_session", "DEFAULT_SESSION_GAP"):
        assert not hasattr(logic, legacy)


def test_only_one_in_progress_episode_per_fic_is_possible(cur):
    from tests.tracker.helpers import T0, seed_fic

    seed_fic(cur, 6301)
    insert = """
        INSERT INTO return_episodes (fic_id, started_at, last_activity_at, previous_max_chapter,
                                     previous_consumption_at, revisited_chapters, current_max_chapter, status)
        VALUES (6301, %s, %s, 4, %s, '{}', 4, %s::episode_status)
    """
    cur.execute(insert, (T0, T0, T0, "in_progress"))
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(insert, (T0, T0, T0, "in_progress"))
    # Any number of RESOLVED episodes is fine.
    cur.execute(insert, (T0, T0, T0, "resolved_return"))
    cur.execute(insert, (T0, T0, T0, "resolved_reread"))


def test_deleting_a_fic_removes_its_behaviour_and_episodes(cur):
    from tests.tracker.helpers import DAY, progress, read_through, seed_fic, episodes, behaviour_state

    fic = seed_fic(cur, 6302)
    last = read_through(cur, fic, upto=4)
    progress(cur, fic, chapter=2, destination=3, at=last + 5 * DAY)
    assert episodes(cur, 6302)

    cur.execute("DELETE FROM fics WHERE fic_id = 6302")

    assert episodes(cur, 6302) == []
    assert behaviour_state(cur, 6302) is None
