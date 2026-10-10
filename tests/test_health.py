from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app


class FakeSession:
    def __init__(self, error: Exception | None = None):
        self.error = error

    async def exec(self, statement):
        if self.error:
            raise self.error


def client_with(session: FakeSession) -> TestClient:
    async def override():
        yield session

    app.dependency_overrides[get_session] = override
    # Not used as a context manager, so the lifespan (and its DB calls) never runs.
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_ok():
    response = client_with(FakeSession()).get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_unavailable():
    error = OperationalError("SELECT 1", {}, Exception("connection refused"))
    response = client_with(FakeSession(error)).get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
