"""Tests create isolated databases and never use the configured application database."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.settings import Settings
from db.repository import Repository

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture
def repository(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path / 'test.db'}")
    yield repo
    repo.engine.dispose()


@pytest.fixture
def client(repository):
    settings = Settings(_env_file=None, openai_api_key="")
    with TestClient(create_app(settings, repository)) as instance:
        yield instance


@pytest.fixture
def sample():
    return (SAMPLES / "db_timeout.jsonl").read_bytes()
