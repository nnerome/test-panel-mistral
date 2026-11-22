"""Live-Postgres fixtures: every test runs against a freshly created schema plus the fake seed.

Requires DATABASE_URL to point at a reachable Postgres (locally: `mistral dev`'s database, or any
DATABASE_URL you export). Registered from tests/conftest.py via pytest_plugins.

The engine is disposed around each test because db.engine caches one global engine, and a
cached AsyncEngine is bound to the event loop that first used it — pytest-asyncio gives each
test its own loop.
"""

import pytest
from db import metadata
from db.engine import dispose_engine, get_engine, get_session_maker

from api.bank.seed import seed_if_empty


@pytest.fixture()
async def db():
    """A session-maker bound to a schema that was just dropped and recreated."""
    await dispose_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    yield get_session_maker()
    await dispose_engine()


@pytest.fixture()
async def seeded(db):
    """`db` plus the 3 fictional customers / accounts / cards / agencies."""
    await seed_if_empty(db)
    return db
