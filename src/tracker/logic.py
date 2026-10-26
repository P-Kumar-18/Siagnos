from datetime import datetime, timedelta
from math import ceil
from typing import Any, Dict, Optional

from psycopg import Cursor

from src.tracker.models import EventType, TrackingEvent


RETURN_INACTIVITY_THRESHOLD = timedelta(hours=24)
REREAD_MINIMUM_INTERVAL = timedelta(days=30)
REREAD_FRACTION = 0.40
REREAD_CHAPTER_CAP = 15


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


def reread_threshold(previously_consumed_chapters: int) -> int:
    """
    Calculate the number of previously consumed chapters that must be
    meaningfully revisited before a return episode qualifies as a
    confirmed reread.

    Stage 4 rule:

        min(ceil(previously_consumed_chapters * 0.40), 15)

    The value 15 is a cap, not a minimum.
    """

    if previously_consumed_chapters < 0:
        raise ValueError(
            "previously_consumed_chapters cannot be negative"
        )

    return min(
        ceil(previously_consumed_chapters * REREAD_FRACTION),
        REREAD_CHAPTER_CAP,
    )


def _is_return_boundary(
    previous_activity_at: Optional[datetime],
    event_timestamp: datetime,
) -> bool:
    """
    Determine whether the current confirmed activity occurs after
    the required inactivity period.

    A return boundary requires at least 24 hours since the previous
    confirmed activity.
    """

    if previous_activity_at is None:
        return False

    return (
        event_timestamp - previous_activity_at
    ) >= RETURN_INACTIVITY_THRESHOLD


def _confirmed_chapter_for_event(
    event: TrackingEvent,
    prior_chapters_read: int,
) -> int:
    """
    Return the chapter position whose consumption this confirmed event
    actually credits.

    Navigation destination is not automatically consumption. The
    existing bucket rules determine which chapter is confirmed:

      - Bucket 1 progress: the destination is previously consumed and
        is the revisited chapter.
      - Bucket 2 progress: the chapter being left is confirmed.
      - Confirmed close/confirmation: the current chapter is confirmed.

    Unresolved Bucket 3 events never reach this helper.
    """

    if event.event_type == EventType.PROGRESS:
        destination = event.destination_chapter
        assert destination is not None

        if destination <= prior_chapters_read:
            return destination

        if destination == event.chapter_number + 1:
            return event.chapter_number

        raise ValueError(
            "Cannot determine a confirmed chapter for an unresolved "
            "progress event"
        )

    return event.chapter_number


def _revisited_chapters_for_event(
    event: TrackingEvent,
    previous_max_chapter: int,
) -> set[int]:
    """
    Return the previously consumed chapter positions that this event
    meaningfully revisits.

    Only unique chapter positions are returned.

    For a progress event:
      - a backward/old destination represents revisiting that
        destination chapter;
      - clean forward progress confirms consumption of the current
        chapter being left, if that chapter was previously consumed.

    For close/confirmation events:
      - the chapter being closed/confirmed is revisited if it was
        previously consumed.
    """

    revisited: set[int] = set()

    if event.event_type == EventType.PROGRESS:
        destination = event.destination_chapter
        assert destination is not None

        if destination <= previous_max_chapter:
            revisited.add(destination)

        # Clean forward movement confirms consumption of the chapter being
        # left. Count it as revisited too when it belongs to prior history.
        # This includes Chapter 1 when moving from Chapter 1 to Chapter 2.
        if (
            destination == event.chapter_number + 1
            and event.chapter_number <= previous_max_chapter
        ):
            revisited.add(event.chapter_number)

    else:
        if event.chapter_number <= previous_max_chapter:
            revisited.add(event.chapter_number)

    return revisited


def _episode_qualifies_as_reread(
    previous_max_chapter: int,
    previous_consumption_at: datetime,
    revisited_chapters: set[int],
    event_timestamp: datetime,
) -> bool:
    """
    Determine whether a completed return episode qualifies as a
    confirmed reread.

    Requirements:

      1. At least 30 days since the relevant previous consumption.
      2. Enough unique previously consumed chapters were revisited.

    Continuation is checked separately and takes precedence.
    """

    if (
        event_timestamp - previous_consumption_at
    ) < REREAD_MINIMUM_INTERVAL:
        return False

    required_chapters = reread_threshold(previous_max_chapter)

    return len(revisited_chapters) >= required_chapters


def _resolve_episode(
    episode: Dict[str, Any],
    resolution_timestamp: datetime,
) -> str:
    """
    Determine the final status of a completed return episode.

    Resolution precedence:

      1. continuation
      2. reread
      3. ordinary return
    """

    previous_max_chapter = episode["previous_max_chapter"]
    current_max_chapter = episode["current_max_chapter"]

    if current_max_chapter > previous_max_chapter:
        return "resolved_continuation"

    revisited_chapters = set(
        episode["revisited_chapters"] or []
    )

    if _episode_qualifies_as_reread(
        previous_max_chapter=previous_max_chapter,
        previous_consumption_at=episode["previous_consumption_at"],
        revisited_chapters=revisited_chapters,
        event_timestamp=episode["started_at"],
    ):
        return "resolved_reread"

    return "resolved_return"


def _get_active_episode(
    cursor: Cursor,
    fic_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve the single active return episode for a fic, if one exists.
    """

    cursor.execute(
        """
        SELECT
            episode_id,
            fic_id,
            started_at,
            last_activity_at,
            previous_max_chapter,
            previous_consumption_at,
            revisited_chapters,
            current_max_chapter,
            status
        FROM return_episodes
        WHERE fic_id = %s
          AND status = 'in_progress'::episode_status
        """,
        (fic_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return {
        "episode_id": row[0],
        "fic_id": row[1],
        "started_at": row[2],
        "last_activity_at": row[3],
        "previous_max_chapter": row[4],
        "previous_consumption_at": row[5],
        "revisited_chapters": row[6] or [],
        "current_max_chapter": row[7],
        "status": row[8],
    }


def _create_return_episode(
    cursor: Cursor,
    fic_id: int,
    event: TrackingEvent,
    previous_max_chapter: int,
    previous_consumption_at: datetime,
) -> Dict[str, Any]:
    """
    Create a new in-progress return episode.

    The episode begins with the current confirmed event.
    """

    current_max_chapter = _confirmed_chapter_for_event(
        event=event,
        prior_chapters_read=previous_max_chapter,
    )

    revisited_chapters = _revisited_chapters_for_event(
        event=event,
        previous_max_chapter=previous_max_chapter,
    )

    cursor.execute(
        """
        INSERT INTO return_episodes (
            fic_id,
            started_at,
            last_activity_at,
            previous_max_chapter,
            previous_consumption_at,
            revisited_chapters,
            current_max_chapter,
            status
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            'in_progress'::episode_status
        )
        RETURNING
            episode_id,
            fic_id,
            started_at,
            last_activity_at,
            previous_max_chapter,
            previous_consumption_at,
            revisited_chapters,
            current_max_chapter,
            status
        """,
        (
            fic_id,
            event.timestamp,
            event.timestamp,
            previous_max_chapter,
            previous_consumption_at,
            sorted(revisited_chapters),
            current_max_chapter,
        ),
    )

    row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Failed to create return episode"
        )

    return {
        "episode_id": row[0],
        "fic_id": row[1],
        "started_at": row[2],
        "last_activity_at": row[3],
        "previous_max_chapter": row[4],
        "previous_consumption_at": row[5],
        "revisited_chapters": row[6] or [],
        "current_max_chapter": row[7],
        "status": row[8],
    }


def _update_return_episode(
    cursor: Cursor,
    episode: Dict[str, Any],
    event: TrackingEvent,
    chapters_read: int,
) -> Dict[str, Any]:
    """
    Add confirmed activity to an existing return episode.

    The episode remains in_progress. Resolution happens only when
    a later confirmed activity establishes a new >=24 hour inactivity
    boundary.
    """

    previous_max_chapter = episode["previous_max_chapter"]

    confirmed_chapter = _confirmed_chapter_for_event(
        event=event,
        prior_chapters_read=chapters_read,
    )

    current_max_chapter = max(
        episode["current_max_chapter"],
        confirmed_chapter,
    )

    revisited_chapters = set(
        episode["revisited_chapters"] or []
    )

    revisited_chapters.update(
        _revisited_chapters_for_event(
            event=event,
            previous_max_chapter=previous_max_chapter,
        )
    )

    updated_revisited_chapters = sorted(revisited_chapters)

    cursor.execute(
        """
        UPDATE return_episodes
        SET
            last_activity_at = GREATEST(last_activity_at, %s),
            revisited_chapters = %s,
            current_max_chapter = %s
        WHERE episode_id = %s
        RETURNING
            episode_id,
            fic_id,
            started_at,
            last_activity_at,
            previous_max_chapter,
            previous_consumption_at,
            revisited_chapters,
            current_max_chapter,
            status
        """,
        (
            event.timestamp,
            updated_revisited_chapters,
            current_max_chapter,
            episode["episode_id"],
        ),
    )

    row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Failed to update return episode"
        )

    return {
        "episode_id": row[0],
        "fic_id": row[1],
        "started_at": row[2],
        "last_activity_at": row[3],
        "previous_max_chapter": row[4],
        "previous_consumption_at": row[5],
        "revisited_chapters": row[6] or [],
        "current_max_chapter": row[7],
        "status": row[8],
    }


def _resolve_return_episode(
    cursor: Cursor,
    episode: Dict[str, Any],
    resolution_timestamp: datetime,
) -> str:
    """
    Resolve an in-progress episode and return its final status.

    The episode is resolved exactly once.
    """

    resolved_status = _resolve_episode(
        episode=episode,
        resolution_timestamp=resolution_timestamp,
    )

    cursor.execute(
        """
        UPDATE return_episodes
        SET status = %s::episode_status
        WHERE episode_id = %s
          AND status = 'in_progress'::episode_status
        """,
        (
            resolved_status,
            episode["episode_id"],
        ),
    )

    if cursor.rowcount != 1:
        raise RuntimeError(
            "Return episode could not be resolved"
        )

    return resolved_status


def process_tracking_event(
    cursor: Cursor,
    event: TrackingEvent,
    fic_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    fic_id = event.fic_id

    # Serialize concurrent events for the same fic for the whole transaction.
    # FOR UPDATE below cannot lock a behaviour row that does not exist yet.
    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (fic_id,))

    # ------------------------------------------------------------------
    # 1. Retrieve current behaviour state
    # ------------------------------------------------------------------

    cursor.execute(
        """
        SELECT
            chapters_read,
            reading_progress,
            return_visits,
            closed_at
        FROM behaviour
        WHERE fic_id = %s
        FOR UPDATE
        """,
        (fic_id,),
    )

    existing = cursor.fetchone()

    if existing:
        prior_chapters_read = existing[0] or 0
        prior_progress = existing[1]
        prior_return_visits = existing[2] or 0
        prior_closed_at = existing[3]
    else:
        prior_chapters_read = 0
        prior_progress = "reading"
        prior_return_visits = 0
        prior_closed_at = None

    # ------------------------------------------------------------------
    # 2. Classify the tracking event
    #
    # We do this before touching return episodes.
    #
    # An unresolved Bucket 3 event must not mutate behavioural state.
    # ------------------------------------------------------------------

    is_bucket_confirmed = False
    new_chapters_read = prior_chapters_read
    new_closed_at = prior_closed_at

    if event.is_confirmation:
        # Bucket 3 resolution:
        # The client confirms the previously unresolved close.
        #
        # IMPORTANT:
        # event.timestamp must contain the ORIGINAL pending close
        # timestamp captured when the unresolved event occurred.
        # It must not be the later time at which the user answered
        # the prompt.

        is_bucket_confirmed = True

        new_chapters_read = max(
            prior_chapters_read,
            event.chapter_number,
        )

        new_closed_at = event.timestamp

    elif event.event_type == EventType.PROGRESS:
        destination = event.destination_chapter
        assert destination is not None

        if destination <= prior_chapters_read:
            # Bucket 1:
            # Progress into already-consumed territory.

            is_bucket_confirmed = True
            new_closed_at = event.timestamp

        elif destination == event.chapter_number + 1:
            # Bucket 2:
            # Clean progress (N+1).
            #
            # Confirms the chapter being left, not the destination.

            is_bucket_confirmed = True

            new_chapters_read = max(
                prior_chapters_read,
                event.chapter_number,
            )

            new_closed_at = event.timestamp

        else:
            # Bucket 3:
            # Unresolved jump.

            is_bucket_confirmed = False

    elif event.event_type == EventType.CLOSE:
        if event.chapter_number <= prior_chapters_read:
            # Bucket 1:
            # Closing an already-consumed chapter.

            is_bucket_confirmed = True
            new_closed_at = event.timestamp

        else:
            # Bucket 3:
            # Unresolved close requiring client-side resolution.

            is_bucket_confirmed = False

    # ------------------------------------------------------------------
    # 3. Guard unresolved events
    # ------------------------------------------------------------------

    if not is_bucket_confirmed:
        return {
            "fic_id": fic_id,
            "chapters_read": prior_chapters_read,
            "reading_progress": prior_progress,
            "return_visits": prior_return_visits,
            "closed_at": prior_closed_at,
            "episode_id": None,
            "episode_status": None,
            "return_visit_recorded": False,
            "written": False,
            "reason": (
                "Unresolved event pending client-side prompt "
                "or adjacent resolution"
            ),
        }

    # ------------------------------------------------------------------
    # 4. Return episode processing
    #
    # There are only two episode situations:
    #
    # A. No active episode:
    #       if >=24h since previous confirmed activity, start one.
    #
    # B. Active episode exists:
    #       if <24h, continue it.
    #       if >=24h, resolve the old episode and start a new one.
    #
    # Importantly, an episode is NOT resolved merely because it has
    # already achieved continuation or reread conditions. It remains
    # in_progress until the next >=24h inactivity boundary.
    # ------------------------------------------------------------------

    active_episode = _get_active_episode(
        cursor=cursor,
        fic_id=fic_id,
    )

    resolved_episode_status = None
    resolved_episode_id = None
    return_visit_recorded = False
    current_episode = None

    return_boundary = _is_return_boundary(
        previous_activity_at=prior_closed_at,
        event_timestamp=event.timestamp,
    )

    if active_episode is not None:
        episode_boundary = _is_return_boundary(
            previous_activity_at=active_episode["last_activity_at"],
            event_timestamp=event.timestamp,
        )

        if episode_boundary:
            # The previous return episode has ended.
            #
            # The current event belongs to the NEW episode, not the
            # previous one.

            resolved_episode_status = _resolve_return_episode(
                cursor=cursor,
                episode=active_episode,
                resolution_timestamp=event.timestamp,
            )

            resolved_episode_id = active_episode["episode_id"]

            # Every successfully resolved return episode counts as
            # exactly one return visit.
            new_return_visits = prior_return_visits + 1
            return_visit_recorded = True

            # The current confirmed activity begins a new episode.
            #
            # The behaviour value already represents the furthest
            # confirmed chapter before this event.
            current_episode = _create_return_episode(
                cursor=cursor,
                fic_id=fic_id,
                event=event,
                previous_max_chapter=prior_chapters_read,
                previous_consumption_at=prior_closed_at,
            )

        else:
            # Same return episode is still active.
            current_episode = _update_return_episode(
                cursor=cursor,
                episode=active_episode,
                event=event,
                chapters_read=prior_chapters_read,
            )

            new_return_visits = prior_return_visits

    elif return_boundary:
        # No active episode exists, but the reader has returned after
        # the required inactivity period.
        #
        # A previous confirmed consumption timestamp is required in
        # order to create a valid episode.

        if prior_closed_at is not None:
            current_episode = _create_return_episode(
                cursor=cursor,
                fic_id=fic_id,
                event=event,
                previous_max_chapter=prior_chapters_read,
                previous_consumption_at=prior_closed_at,
            )

        new_return_visits = prior_return_visits

    else:
        # Ordinary activity with no return episode.
        new_return_visits = prior_return_visits

    # ------------------------------------------------------------------
    # 5. Derive updated reading_progress
    # ------------------------------------------------------------------

    new_progress = derive_reading_progress(
        chapters_read=new_chapters_read,
        current_chapters=fic_metadata.get("current_chapters", 1),
        total_chapters=fic_metadata.get("total_chapters"),
        status=fic_metadata.get("status"),
    )

    # ------------------------------------------------------------------
    # 6. Persist confirmed behaviour
    # ------------------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO behaviour (
            fic_id,
            chapters_read,
            reading_progress,
            return_visits,
            closed_at
        )
        VALUES (%s, %s, %s::reading_status, %s, %s)
        ON CONFLICT (fic_id) DO UPDATE SET
            chapters_read = GREATEST(
                behaviour.chapters_read,
                EXCLUDED.chapters_read
            ),
            reading_progress = EXCLUDED.reading_progress,
            return_visits = EXCLUDED.return_visits,
            closed_at = CASE
                WHEN behaviour.closed_at IS NULL
                    THEN EXCLUDED.closed_at
                WHEN EXCLUDED.closed_at IS NULL
                    THEN behaviour.closed_at
                ELSE GREATEST(
                    behaviour.closed_at,
                    EXCLUDED.closed_at
                )
            END;
        """,
        (
            fic_id,
            new_chapters_read,
            new_progress,
            new_return_visits,
            new_closed_at,
        ),
    )

    # ------------------------------------------------------------------
    # 7. Return processing result
    # ------------------------------------------------------------------

    return {
        "fic_id": fic_id,
        "chapters_read": new_chapters_read,
        "reading_progress": new_progress,
        "return_visits": new_return_visits,
        "closed_at": new_closed_at,
        "episode_id": (
            current_episode["episode_id"]
            if current_episode is not None
            else resolved_episode_id
        ),
        "episode_status": (
            current_episode["status"]
            if current_episode is not None
            else resolved_episode_status
        ),
        "resolved_episode_id": resolved_episode_id,
        "resolved_episode_status": resolved_episode_status,
        "return_visit_recorded": return_visit_recorded,
        "written": True,
    }
    
