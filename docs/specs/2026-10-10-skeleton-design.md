# project-gsd skeleton — design

**Date:** 2026-10-10
**Status:** Approved

## Goal

A minimal, reusable template for a Python API service: FastAPI, Pydantic,
SQLModel and MySQL. It should be small enough to read in one sitting, fast to
recreate from scratch, and complete enough to clone and run.

No build system beyond `pip` and `pyproject.toml`. Adding a dependency is one
`pip install`; adding an endpoint is one new file.

## Success criteria

From a fresh clone, on macOS with Python 3.14 and Podman:

1. `pytest -q` passes without a database running.
2. `podman compose up -d` starts MySQL.
3. `uvicorn app.main:app --reload` serves on `localhost:8000`:
   - `GET /health` → `200 {"status": "ok"}`
   - `GET /health/db` → `200 {"status": "ok"}` when MySQL is up, `503` when it's down
   - `GET /docs` shows Swagger UI
4. The repo contains no secrets.

## Stack (versions checked 2026-10-10)

| Layer | Choice |
|---|---|
| Language | Python 3.14 |
| Packaging | `pyproject.toml`, local `.venv`, `pip install -e ".[dev]"` |
| API | FastAPI 0.143, Uvicorn 0.54 |
| Validation / config | Pydantic 2.14, pydantic-settings 2.15 |
| ORM | SQLModel 0.0.48 on async SQLAlchemy 2.1 |
| MySQL driver | asyncmy 0.2.16 (`mysql+asyncmy://`), plus `cryptography` for MySQL 8.4's default `caching_sha2_password` auth |
| Database | MySQL 8.4 LTS, `docker.io/library/mysql:8.4`, run with Podman |
| Tests | pytest, FastAPI `TestClient` (httpx2, which Starlette now prefers over httpx) |

Dependencies in `pyproject.toml` use lower bounds (`>=`) at the versions above.

## Layout

```
project-gsd/
  pyproject.toml
  compose.yaml            # MySQL only; works with `podman compose` or `docker compose`
  .env.example  .gitignore  README.md
  app/
    main.py               # app + lifespan: create tables on startup, dispose engine on shutdown
    settings.py           # Settings(BaseSettings): database_url, from env / .env
    db.py                 # async engine, session factory, get_session() dependency
    routes/health.py      # /health and /health/db
  tests/
    test_health.py
  docs/specs/
```

## Components

- **settings.py:** one `Settings` class. `database_url` is read from the
  environment or an optional `.env` file. Its default points at the local
  compose MySQL, so the app runs with no config. `.env.example` documents it;
  `.env` is gitignored.
- **db.py:** `create_async_engine(settings.database_url, pool_pre_ping=True)`,
  an `async_sessionmaker` producing `sqlmodel.ext.asyncio.session.AsyncSession`,
  and an async `get_session()` generator used as a FastAPI dependency.
  Creating the engine does not connect.
- **main.py:** the lifespan runs `SQLModel.metadata.create_all` on startup
  and disposes the engine on shutdown, so startup fails fast if MySQL is
  unreachable. It mounts the health router.
- **routes/health.py:** `/health` is liveness only and never touches the DB.
  `/health/db` runs `SELECT 1` through the session. On a database error it
  returns `503 {"status": "unavailable"}` and logs the exception.

## Schema changes

The skeleton uses `create_all`, which creates missing tables but never alters
existing ones. Add Alembic once the schema needs to evolve with data in place.

## Testing

`tests/test_health.py` uses `TestClient` with `get_session` overridden by a
fake, and the startup table creation disabled, so no MySQL is needed:

- `/health` returns 200.
- `/health/db` returns 200 when the fake session succeeds.
- `/health/db` returns 503 when the fake raises `OperationalError`.

## Out of scope (possible later additions)

Domain models and CRUD, Alembic migrations, container image, Kubernetes
manifests, CI, auth, structured logging, integration tests against a real
MySQL, linting and formatting.
