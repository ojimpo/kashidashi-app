from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


@pytest.fixture
def app(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    return create_app(Settings(database_url=database_url))


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client

