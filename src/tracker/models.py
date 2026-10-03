from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    PROGRESS = "progress"
    CLOSE = "close"


class RatingType(str, Enum):
    DISLIKED = "disliked"
    LIKED = "liked"
    LOVED = "loved"


class TrackingEvent(BaseModel):
    fic_id: int = Field(..., gt=0)
    chapter_number: int = Field(..., gt=0)
    event_type: EventType
    destination_chapter: Optional[int] = Field(None, gt=0)
    timestamp: datetime
    rating: Optional[RatingType] = None
    is_confirmation: bool = False  # Explicitly flags a Bucket 3 prompt resolution

    @model_validator(mode="after")
    def validate_event_structure(self) -> "TrackingEvent":
        # Convert to UTC first, then strip timezone for PostgreSQL compatibility
        if self.timestamp.tzinfo is not None:
            self.timestamp = self.timestamp.astimezone(timezone.utc).replace(tzinfo=None)

        if self.event_type == EventType.PROGRESS:
            if self.destination_chapter is None:
                raise ValueError(
                    "destination_chapter is required when event_type is 'progress'"
                )
            if self.rating is not None:
                raise ValueError(
                    "Ratings are only permitted on 'close' events (bucket 3 prompts)"
                )
        elif self.event_type == EventType.CLOSE:
            if self.destination_chapter is not None:
                raise ValueError(
                    "destination_chapter must not be provided when event_type is 'close'"
                )

        if self.is_confirmation and self.event_type != EventType.CLOSE:
            raise ValueError(
                "is_confirmation is only permitted on 'close' events"
            )
        return self