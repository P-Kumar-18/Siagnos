"""Spec section 12: the fic must be resolved or ingested before any behavior write.

These tests replace the resolver, ingestion service, DB connection and
process_tracking_event with recorders, so they check ORDER and GATING only, not
behavior rules.
"""
import pytest

PAYLOAD = {
    "fic_id": 555,
    "chapter_number": 2,
    "event_type": "progress",
    "destination_chapter": 3,
    "timestamp": "2026-01-01T10:00:00Z",
}


class Recorder:
    def __init__(self, resolve_result=None, ingest_result=None, metadata_row=(12, None, "on_going")):
        self.calls = []
        self.resolve_result = resolve_result if resolve_result is not None else {"fic_id": 555}
        self.ingest_result = ingest_result if ingest_result is not None else {}
        self.metadata_row = metadata_row

    def resolve(self, payload):
        self.calls.append("resolve")
        return self.resolve_result

    def ingest(self, payload):
        self.calls.append("ingest")
        return self.ingest_result

    def get_connection(self):
        self.calls.append("get_connection")
        recorder = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                recorder.calls.append("select_metadata")

            def fetchone(self):
                return recorder.metadata_row

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def cursor(self):
                return Cursor()

            def commit(self):
                recorder.calls.append("commit")

        return Connection()

    def process(self, cursor, event, metadata):
        self.calls.append("process")
        return {"fic_id": event.fic_id, "written": True}


@pytest.fixture
def client(load_routes, monkeypatch):
    def _build(recorder):
        routes, test_client = load_routes(
            resolve=recorder.resolve,
            ingest=recorder.ingest,
            get_connection=recorder.get_connection,
        )
        monkeypatch.setattr(routes, "process_tracking_event", recorder.process)
        return test_client

    return _build


def test_known_fic_is_written_without_ingestion(client):
    rec = Recorder()
    response = client(rec).post("/tracker/event", json=PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"fic_id": 555, "written": True}
    assert "ingest" not in rec.calls
    assert rec.calls.index("resolve") < rec.calls.index("process")


def test_unknown_fic_is_ingested_before_any_database_access_or_write(client):
    rec = Recorder(resolve_result={"error": "not found"}, ingest_result={"fic_id": 555})
    response = client(rec).post("/tracker/event", json=PAYLOAD)

    assert response.status_code == 200
    order = rec.calls
    assert order.index("resolve") < order.index("ingest") < order.index("get_connection")
    assert order.index("ingest") < order.index("process")


def test_failed_ingestion_returns_404_and_writes_nothing(client):
    rec = Recorder(resolve_result={"error": "not found"}, ingest_result={"error": "AO3 unreachable"})
    response = client(rec).post("/tracker/event", json=PAYLOAD)

    assert response.status_code == 404
    assert "AO3 unreachable" in response.text
    for forbidden in ("get_connection", "process", "commit"):
        assert forbidden not in rec.calls


def test_fic_missing_after_resolution_returns_404_and_writes_nothing(client):
    rec = Recorder(metadata_row=None)
    response = client(rec).post("/tracker/event", json=PAYLOAD)

    assert response.status_code == 404
    assert "process" not in rec.calls
    assert "commit" not in rec.calls


def test_invalid_payload_is_rejected_before_resolution(client):
    rec = Recorder()
    bad = {k: v for k, v in PAYLOAD.items() if k != "destination_chapter"}
    response = client(rec).post("/tracker/event", json=bad)

    assert response.status_code == 422
    assert rec.calls == []


def test_extension_payload_with_tab_and_window_ids_is_accepted(client):
    rec = Recorder()
    response = client(rec).post("/tracker/event", json={**PAYLOAD, "tab_id": 4, "window_id": 1})

    assert response.status_code == 200
    assert "process" in rec.calls
