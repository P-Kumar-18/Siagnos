import importlib
import sys
import types

import pytest


@pytest.fixture
def load_routes(monkeypatch, request):
    """Import a fresh src.tracker.routes with its three collaborators replaced.

    routes.py imports get_connection, FicResolver and IngestionService at module
    level, so they are swapped in through sys.modules before the import. Calling the
    returned loader again re-imports routes from scratch, which is how tests
    simulate an API restart (no module-level state survives).

    resolve(payload) -> dict      "error" key means "not found locally"
    ingest(payload)  -> dict      "error" key means ingestion failed
    get_connection() -> connection usable as a context manager
    """

    def _load(*, resolve, ingest, get_connection):
        class FicResolver:
            def __init__(self, payload):
                self.payload = payload

            def resolve(self):
                return resolve(self.payload)

        class IngestionService:
            def __init__(self, payload):
                self.payload = payload

            def ingest(self):
                return ingest(self.payload)

        fakes = {
            "src.loader.database": ("get_connection", get_connection),
            "src.services.fic_resolver": ("FicResolver", FicResolver),
            "src.services.ingestion_service": ("IngestionService", IngestionService),
        }
        for name, (attr, value) in fakes.items():
            module = types.ModuleType(name)
            setattr(module, attr, value)
            monkeypatch.setitem(sys.modules, name, module)

        sys.modules.pop("src.tracker.routes", None)
        routes = importlib.import_module("src.tracker.routes")

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(routes.router)
        return routes, TestClient(app)

    request.addfinalizer(lambda: sys.modules.pop("src.tracker.routes", None))
    return _load
