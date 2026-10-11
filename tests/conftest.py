import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.main import app

# Root on the compose MySQL, so the test database can be created without an init script.
SERVER_URL = os.environ.get("TEST_MYSQL_URL", "mysql+asyncmy://root:root@127.0.0.1:3306")
TEST_DB = "fieldops_test"


async def _create_database() -> None:
    engine = create_async_engine(SERVER_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {TEST_DB}"))
    await engine.dispose()


async def _reset_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


@pytest.fixture(scope="session")
def engine() -> AsyncEngine:
    asyncio.run(_create_database())
    # NullPool: no connection outlives the event loop that opened it. TestClient and
    # asyncio.run each use their own loop.
    return create_async_engine(f"{SERVER_URL}/{TEST_DB}", poolclass=NullPool)


@pytest.fixture
def clean_db(engine: AsyncEngine) -> AsyncEngine:
    asyncio.run(_reset_tables(engine))
    return engine


@pytest.fixture
def run_db(clean_db: AsyncEngine):
    """Run an async function with a fresh session, e.g. to seed rows or read them back."""
    engine = clean_db

    def run(fn):
        async def go():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                return await fn(session)

        return asyncio.run(go())

    return run


@pytest.fixture
def client(clean_db: AsyncEngine):
    engine = clean_db

    async def override():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override
    # Not used as a context manager, so the app's lifespan (production engine) never runs.
    yield TestClient(app)
    app.dependency_overrides.clear()
