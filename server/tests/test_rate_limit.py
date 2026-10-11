from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Base
from app.factory import create_app
from tests.conftest import auth_header, register_account


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
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    with TestClient(application) as client:
        yield client
    application.state.engine.dispose()


def test_register_rate_limited(limited_client: TestClient) -> None:
    last = None
    for i in range(15):
        response = limited_client.post(
            "/api/v1/auth/register",
            json={"email": f"rate{i}@example.com", "password": "password123"},
        )
        last = response.status_code
    assert last == 429


def test_limiter_disabled_in_default_tests(client: TestClient) -> None:
    token = register_account(client)
    for _ in range(5):
        assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 200
