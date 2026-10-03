from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from psycopg import Cursor

from src.tracker.models import EventType, TrackingEvent

DEFAULT_SESSION_GAP = timedelta(hours=2)


def derive_reading_progress(
    chapters_read: int,
    current_chapters: int,
    total_chapters: Optional[int],
    status: Optional[str],
) -> str:
    if (
        status == "completed"
        and total_chapters is not None
        and chapters_read >= total_chapters
    ):
        return "completed"
    if status == "on_going" and chapters_read >= current_chapters:
        return "up_to_date"
    return "reading"


def is_new_session(
    current_closed_at: Optional[datetime],
    event_timestamp: datetime,
    max_other_closed_at: Optional[datetime],
    threshold: timedelta = DEFAULT_SESSION_GAP,
) -> bool:
    if current_closed_at is None:
        return False

    time_elapsed_exceeded = (event_timestamp - current_closed_at) > threshold
    read_other_fic_in_between = (
        max_other_closed_at is not None and max_other_closed_at > current_closed_at
    )

    return time_elapsed_exceeded or read_other_fic_in_between


def process_tracking_event(
    cursor: Cursor,
    event: TrackingEvent,
    fic_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    fic_id = event.fic_id

    # 1. Retrieve current behaviour state
    cursor.execute(
        """
        SELECT chapters_read, reading_progress, return_visits, ratings, closed_at
        FROM behaviour
        WHERE fic_id = %s
        """,
        (fic_id,),
    )
    existing = cursor.fetchone()

    if existing:
        prior_chapters_read = existing[0] or 0
        prior_progress = existing[1]
        prior_return_visits = existing[2] or 0
        prior_rating = existing[3]
        prior_closed_at = existing[4]
    else:
        prior_chapters_read = 0
        prior_progress = "reading"
        prior_return_visits = 0
        prior_rating = None
        prior_closed_at = None

    # 2. Evaluate session boundary against other fics
    cursor.execute(
        """
        SELECT MAX(closed_at)
        FROM behaviour
        WHERE fic_id != %s AND closed_at IS NOT NULL
        """,
        (fic_id,),
    )
    row = cursor.fetchone()
    max_other_closed_at = row[0] if row and row[0] is not None else None

    new_session = is_new_session(prior_closed_at, event.timestamp, max_other_closed_at)

    is_bucket_confirmed = False
    new_chapters_read = prior_chapters_read
    new_closed_at = prior_closed_at
    new_return_visits = prior_return_visits
    new_rating = prior_rating

    rating_updated = False
    if event.rating is not None:
        new_rating = event.rating.value
        rating_updated = True

    # 3. Bucket classification
    if event.is_confirmation:
        # Bucket 3 Resolution: Explicit prompt confirms the uncredited chapter.
        # Contract: The client MUST send the original pending timestamp here.
        is_bucket_confirmed = True
        new_chapters_read = max(prior_chapters_read, event.chapter_number)
        new_closed_at = event.timestamp
        
    elif event.event_type == EventType.PROGRESS:
        dest = event.destination_chapter
        assert dest is not None  # Guaranteed by model_validator

        if dest <= prior_chapters_read:
            # Bucket 1: Reread progress
            is_bucket_confirmed = True
            new_closed_at = event.timestamp
            if new_session:
                new_return_visits += 1
        elif dest == event.chapter_number + 1:
            # Bucket 2: Clean progress (N+1)
            # Confirms the chapter being left, not the destination
            is_bucket_confirmed = True
            new_chapters_read = max(prior_chapters_read, event.chapter_number)
            new_closed_at = event.timestamp
        else:
            # Bucket 3: Unresolved jump
            is_bucket_confirmed = False

    elif event.event_type == EventType.CLOSE:
        if event.chapter_number <= prior_chapters_read:
            # Bucket 1: Closing a reread chapter
            is_bucket_confirmed = True
            new_closed_at = event.timestamp
            if new_session:
                new_return_visits += 1
        else:
            # Bucket 3: Unresolved close (pending client-side resolution)
            is_bucket_confirmed = False

    # Guard: Do not write to DB for unresolved Bucket 3 events
    if not is_bucket_confirmed:
        return {
            "fic_id": fic_id,
            "chapters_read": prior_chapters_read,
            "reading_progress": prior_progress,
            "return_visits": prior_return_visits,
            "ratings": prior_rating,
            "closed_at": prior_closed_at,
            "session_boundary_triggered": new_session,
            "written": False,
            "reason": "Unresolved event pending client-side prompt or adjacent resolution",
        }

    # 4. Derive updated reading_progress state
    new_progress = derive_reading_progress(
        chapters_read=new_chapters_read,
        current_chapters=fic_metadata.get("current_chapters", 1),
        total_chapters=fic_metadata.get("total_chapters"),
        status=fic_metadata.get("status"),
    )

    # 5. Upsert confirmed changes
    cursor.execute(
        """
        INSERT INTO behaviour (
            fic_id,
            chapters_read,
            reading_progress,
            return_visits,
            ratings,
            closed_at
        )
        VALUES (%s, %s, %s::reading_status, %s, %s::rating_types, %s)
        ON CONFLICT (fic_id) DO UPDATE SET
            chapters_read = GREATEST(behaviour.chapters_read, EXCLUDED.chapters_read),
            reading_progress = EXCLUDED.reading_progress,
            return_visits = EXCLUDED.return_visits,
            ratings = COALESCE(EXCLUDED.ratings, behaviour.ratings),
            closed_at = CASE
                WHEN behaviour.closed_at IS NULL THEN EXCLUDED.closed_at
                WHEN EXCLUDED.closed_at IS NULL THEN behaviour.closed_at
                ELSE GREATEST(behaviour.closed_at, EXCLUDED.closed_at)
            END;
        """,
        (
            fic_id,
            new_chapters_read,
            new_progress,
            new_return_visits,
            new_rating,
            new_closed_at,
        ),
    )

    return {
        "fic_id": fic_id,
        "chapters_read": new_chapters_read,
        "reading_progress": new_progress,
        "return_visits": new_return_visits,
        "ratings": new_rating,
        "closed_at": new_closed_at,
        "session_boundary_triggered": new_session,
        "written": True,
    }