from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from app.db import engine
from app.routes import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates missing tables only; it never alters existing ones. Swap for Alembic
    # once the schema needs to change with data in place.
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="fieldops-app", lifespan=lifespan)
app.include_router(health.router)
