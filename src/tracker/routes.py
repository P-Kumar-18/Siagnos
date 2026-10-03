from fastapi import APIRouter, HTTPException

from src.loader.database import get_connection
from src.services.fic_resolver import FicResolver
from src.services.ingestion_service import IngestionService
from src.tracker.logic import process_tracking_event
from src.tracker.models import TrackingEvent


router = APIRouter(
    prefix="/tracker",
    tags=["tracker"],
)


@router.post("/event")
def track_event(event: TrackingEvent):
    # Make sure the fic exists before writing behaviour.
    resolver = FicResolver({"fic_id": event.fic_id})
    fic = resolver.resolve()

    if "error" in fic:
        ingestion = IngestionService({"fic_id": event.fic_id})
        result = ingestion.ingest()

        if "error" in result:
            raise HTTPException(
                status_code=404,
                detail=result["error"],
            )

    # Fetch the current fic metadata needed by the behaviour logic.
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_chapters,
                    total_chapters,
                    status
                FROM fics
                WHERE fic_id = %s
                """,
                (event.fic_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Fic {event.fic_id} was not found after resolution.",
                )

            fic_metadata = {
                "current_chapters": row[0],
                "total_chapters": row[1],
                "status": row[2],
            }

            result = process_tracking_event(
                cursor,
                event,
                fic_metadata,
            )

        connection.commit()

    return result