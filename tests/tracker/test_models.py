"""Contract tests for TrackingEvent, the payload the extension sends.

Ratings are removed from the Stage 4 model, so nothing here constructs or asserts
a rating.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.tracker.models import EventType, TrackingEvent

BASE = {
    "fic_id": 123,
    "chapter_number": 2,
    "event_type": "progress",
    "destination_chapter": 3,
    "timestamp": "2026-01-01T10:00:00Z",
}


def test_valid_progress_event():
    event = TrackingEvent(**BASE)
    assert event.event_type is EventType.PROGRESS
    assert event.destination_chapter == 3
    assert event.is_confirmation is False


def test_valid_close_event():
    payload = {k: v for k, v in BASE.items() if k != "destination_chapter"}
    event = TrackingEvent(**{**payload, "event_type": "close"})
    assert event.event_type is EventType.CLOSE
    assert event.destination_chapter is None


def test_progress_requires_destination_chapter():
    payload = {k: v for k, v in BASE.items() if k != "destination_chapter"}
    with pytest.raises(ValidationError):
        TrackingEvent(**payload)


def test_close_rejects_destination_chapter():
    with pytest.raises(ValidationError):
        TrackingEvent(**{**BASE, "event_type": "close"})


def test_confirmation_flag_only_allowed_on_close():
    with pytest.raises(ValidationError):
        TrackingEvent(**{**BASE, "is_confirmation": True})


def test_confirmation_flag_accepted_on_close():
    payload = {k: v for k, v in BASE.items() if k != "destination_chapter"}
    event = TrackingEvent(**{**payload, "event_type": "close", "is_confirmation": True})
    assert event.is_confirmation is True


@pytest.mark.parametrize("field", ["fic_id", "chapter_number", "destination_chapter"])
@pytest.mark.parametrize("bad", [0, -1])
def test_ids_and_chapters_must_be_positive(field, bad):
    with pytest.raises(ValidationError):
        TrackingEvent(**{**BASE, field: bad})


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        TrackingEvent(**{**BASE, "event_type": "scroll"})


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-01-01T10:00:00Z", datetime(2026, 1, 1, 10, 0, 0)),
        ("2026-01-01T15:30:00+05:30", datetime(2026, 1, 1, 10, 0, 0)),
        ("2026-01-01T10:00:00", datetime(2026, 1, 1, 10, 0, 0)),
    ],
)
def test_timestamp_is_normalised_to_naive_utc(raw, expected):
    event = TrackingEvent(**{**BASE, "timestamp": raw})
    assert event.timestamp == expected
    assert event.timestamp.tzinfo is None


def test_actual_extension_payload_shape_is_accepted():
    """background.js adds tab_id and window_id to every event; they must not break validation."""
    event = TrackingEvent(**{**BASE, "tab_id": 17, "window_id": 3})
    assert event.fic_id == 123
