from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Base
from app.factory import create_app


@pytest.fixture()
def limited_client(tmp_path: Path):
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'rate.db').as_posix()}",
        data_dir=str(tmp_path / "data"),
        rp_id="localhost",
        allowed_origins=["http://localhost:8000"],
        rate_limit_enabled=True,
    )
    application = create_app(settings, allow_unauthenticated_api_for_tests=True)
    Base.metadata.create_all(application.state.engine)
    with TestClient(application) as client:
        yield client
    application.state.engine.dispose()


def test_register_begin_rate_limited(limited_client: TestClient) -> None:
    last = None
    for _ in range(35):
        response = limited_client.post("/api/v1/webauthn/register/begin")
        last = response.status_code
    assert last == 429


def test_limiter_disabled_in_default_tests(client: TestClient) -> None:
    for _ in range(5):
        assert client.get("/api/v1/webauthn/credentials").status_code == 200
