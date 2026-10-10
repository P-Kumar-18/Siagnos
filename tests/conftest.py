"""Shared fixtures for the Siagnos test suite.

Database tests need a THROWAWAY PostgreSQL database. Point SIAGNOS_TEST_DSN at it,
for example:

    SIAGNOS_TEST_DSN="postgresql://postgres:password@localhost:5432/siagnos_test"

Each session creates a private schema from src/database/schema.sql inside that
database and drops it afterwards, so the live `siagnos` database is never touched.
Do not point this at the live database.
"""
import os
import pathlib
import re
import sys
import uuid

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Override with SIAGNOS_SCHEMA_FILE when the canonical schema lives elsewhere.
SCHEMA_FILE = pathlib.Path(
    os.environ.get("SIAGNOS_SCHEMA_FILE", ROOT / "src" / "database" / "schema.sql")
)


def load_schema_ddl(path, schema):
    """Return the schema file as DDL that creates everything inside `schema` only.

    Handles both a hand-written schema.sql and a raw `pg_dump` (including PowerShell's
    UTF-16 output): decodes by BOM, drops psql meta-commands (\\restrict), the
    search_path reset and OWNER TO lines, and re-targets `public.` to the test schema so
    a dump can never create objects in the real `public` schema.
    """
    raw = pathlib.Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("\\"):
            continue
        if "set_config('search_path'" in stripped:
            continue
        if stripped.startswith("SET "):  # pg_dump session header; version-specific, not needed
            continue
        if re.match(r"ALTER .* OWNER TO ", stripped):
            continue
        kept.append(line)
    return "\n".join(kept).replace("public.", f'"{schema}".')


@pytest.fixture(scope="session")
def pg_schema():
    dsn = os.environ.get("SIAGNOS_TEST_DSN")
    if not dsn:
        pytest.skip("SIAGNOS_TEST_DSN is not set (throwaway PostgreSQL database required)")

    import psycopg

    schema = f"siagnos_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    with psycopg.connect(dsn, autocommit=True, options=f"-c search_path={schema}") as conn:
        conn.execute(load_schema_ddl(SCHEMA_FILE, schema))

    yield {"dsn": dsn, "schema": schema}

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.fixture
def connect(pg_schema):
    """Factory returning a NEW autocommit connection bound to the test schema.

    Calling it again simulates a fresh process (API restart) because no
    in-process state is shared between connections. Everything opened during a test is
    closed when the test ends, so a large suite never exhausts max_connections.
    """
    import psycopg

    opened = []

    def _connect():
        conn = psycopg.connect(
            pg_schema["dsn"],
            autocommit=True,
            options=f"-c search_path={pg_schema['schema']}",
        )
        opened.append(conn)
        return conn

    yield _connect
    for conn in opened:
        if not conn.closed:
            conn.close()


@pytest.fixture(autouse=True)
def _clean_tables(request):
    """Empty fics (and everything referencing it) before each DB test."""
    if "connect" not in request.fixturenames:
        yield
        return
    conn = request.getfixturevalue("connect")()
    conn.execute("TRUNCATE fics CASCADE")
    yield


@pytest.fixture
def cur(connect):
    conn = connect()
    with conn.cursor() as cursor:
        yield cursor
