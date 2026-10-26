"""Test helpers. They call only the interfaces that exist today:
TrackingEvent, process_tracking_event, and the behaviour/fics tables.

`behaviour_state` deliberately selects only the columns the Stage 4 model keeps,
so these tests keep working when the legacy `ratings` column is dropped.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.tracker.logic import process_tracking_event
from src.tracker.models import EventType, TrackingEvent

T0 = datetime(2026, 1, 1, 10, 0, 0)  # naive UTC, matches what the model produces
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


@dataclass
class Fic:
    fic_id: int
    current_chapters: int
    total_chapters: Optional[int]
    status: Optional[str]

    @property
    def meta(self):
        return {
            "current_chapters": self.current_chapters,
            "total_chapters": self.total_chapters,
            "status": self.status,
        }


def seed_fic(cursor, fic_id, current_chapters=12, total_chapters=None, status="on_going"):
    cursor.execute(
        """
        INSERT INTO fics (fic_id, url, name, hits, bookmarks, kudos,
                          current_chapters, total_chapters, words, status,
                          language, rating)
        VALUES (%s, %s, %s, 0, 0, 0, %s, %s, 0, %s::status, 'English', 'General Audiences')
        """,
        (
            fic_id,
            f"https://archiveofourown.org/works/{fic_id}",
            f"fic {fic_id}",
            current_chapters,
            total_chapters,
            status,
        ),
    )
    return Fic(fic_id, current_chapters, total_chapters, status)


def progress(cursor, fic, chapter, destination, at):
    """Leave `chapter` by navigating to `destination` (event_type=progress)."""
    event = TrackingEvent(
        fic_id=fic.fic_id,
        chapter_number=chapter,
        event_type=EventType.PROGRESS,
        destination_chapter=destination,
        timestamp=at,
    )
    return process_tracking_event(cursor, event, fic.meta)


def close(cursor, fic, chapter, at, confirmation=False):
    """Leave `chapter` without a known destination (event_type=close).

    confirmation=True is the backend side of the bucket-3 prompt being answered
    yes; `at` must then be the ORIGINAL pending close time.
    """
    event = TrackingEvent(
        fic_id=fic.fic_id,
        chapter_number=chapter,
        event_type=EventType.CLOSE,
        timestamp=at,
        is_confirmation=confirmation,
    )
    return process_tracking_event(cursor, event, fic.meta)


def behaviour_state(cursor, fic_id):
    cursor.execute(
        """
        SELECT chapters_read, return_visits, reading_progress::text, closed_at
        FROM behaviour WHERE fic_id = %s
        """,
        (fic_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "chapters_read": row[0],
        "return_visits": row[1],
        "reading_progress": row[2],
        "closed_at": row[3],
    }


def read_through(cursor, fic, upto, start=T0, step=timedelta(minutes=1)):
    """Click Next from chapter 1 through `upto`, one event per `step`.

    Leaves chapters_read == upto and closed_at == the last event time.
    Returns that last event time.
    """
    at = start
    for chapter in range(1, upto + 1):
        at = start + step * (chapter - 1)
        progress(cursor, fic, chapter, chapter + 1, at)
    return at


# ---- return-episode helpers (Stage 4 return_episodes table) -----------------

_EPISODE_COLUMNS = (
    "episode_id", "fic_id", "started_at", "last_activity_at", "previous_max_chapter",
    "previous_consumption_at", "revisited_chapters", "current_max_chapter", "status",
)


def episodes(cursor, fic_id):
    """All return episodes for a fic, oldest first, as dicts."""
    cursor.execute(
        f"""
        SELECT {", ".join(c if c != "status" else "status::text" for c in _EPISODE_COLUMNS)}
        FROM return_episodes WHERE fic_id = %s ORDER BY episode_id
        """,
        (fic_id,),
    )
    return [dict(zip(_EPISODE_COLUMNS, row)) for row in cursor.fetchall()]


def statuses(cursor, fic_id):
    return [e["status"] for e in episodes(cursor, fic_id)]


def revisit_closes(cursor, fic, chapters, at):
    """Close each known chapter once, all at the same timestamp `at` (bucket 1, no ambiguity
    about which instant an age or gap is measured at)."""
    last = None
    for chapter in chapters:
        last = close(cursor, fic, chapter, at)
    return last


def resolve_by_new_boundary(cursor, fic, last_activity_at, gap=2 * DAY):
    """Send one confirmed event >= 24h after `last_activity_at`. That event resolves the
    open episode and (rule 5) begins the NEW one. Returns its timestamp."""
    at = last_activity_at + gap
    close(cursor, fic, 1, at)  # chapter 1 is always known territory in these scenarios
    return at
