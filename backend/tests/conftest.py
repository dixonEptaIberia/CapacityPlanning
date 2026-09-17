"""Test fixtures: isolated in-memory-ish SQLite DB and a TestClient."""
from __future__ import annotations

import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file before importing app modules.
_tmp_db = os.path.join(tempfile.gettempdir(), "planning_test.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ["AUTH_MODE"] = "dev"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.db.base import init_db
    from app.main import app
    from app.seed import seed_if_empty

    init_db()
    seed_if_empty()
    with TestClient(app) as c:
        yield c
