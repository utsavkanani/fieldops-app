# project-gsd

A minimal FastAPI service template: Pydantic settings, async SQLModel on MySQL,
and pytest. Plain `pip` and `pyproject.toml`, no build system to maintain.

## Stack

Python 3.14 · FastAPI · Uvicorn · Pydantic + pydantic-settings · SQLModel (async SQLAlchemy 2.1) · asyncmy · MySQL 8.4 · pytest

## Quick start

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev]"

podman compose up -d                    # or: docker compose up -d
.venv/bin/uvicorn app.main:app --reload
```

```bash
curl localhost:8000/health              # {"status":"ok"}
curl localhost:8000/health/db           # {"status":"ok"}, or 503 if MySQL is down
open http://localhost:8000/docs         # Swagger UI
```

Configuration comes from environment variables or a `.env` file. See
`.env.example`; the defaults match `compose.yaml`. The app needs MySQL to be
reachable at startup, because it creates tables then.

## Layout

```
app/
  main.py           FastAPI app; lifespan creates tables and disposes the engine
  settings.py       Settings (DATABASE_URL)
  db.py             async engine, session factory, get_session dependency
  routes/health.py  /health and /health/db
tests/              pytest; the DB session is faked, so no MySQL is needed
compose.yaml        MySQL 8.4
```

## Development workflow

| To… | Do |
|---|---|
| Run tests | `.venv/bin/pytest -q` |
| Add a dependency | `.venv/bin/pip install <pkg>`, then add it to `dependencies` in `pyproject.toml` |
| Add an endpoint | Create `app/routes/<name>.py` with an `APIRouter`, then `app.include_router(<name>.router)` in `app/main.py` |
| Add a table | Create a `SQLModel` class with `table=True` and import it in `app/main.py`; it's created on next startup |
| Reset the database | `podman compose down -v && podman compose up -d` |

`create_all` only creates missing tables; it never alters existing ones. Add
Alembic once the schema needs to change with data in place.

## Troubleshooting

**`podman compose up` fails with "error getting credentials".** Podman falls
back to `~/.docker/config.json`, and a Docker Desktop or gcloud credential
helper there can fail. The MySQL image is public, so an empty auth file works:

```bash
echo '{"auths":{}}' > /tmp/empty-auth.json
REGISTRY_AUTH_FILE=/tmp/empty-auth.json podman compose up -d
```
