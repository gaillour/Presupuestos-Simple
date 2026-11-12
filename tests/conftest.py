import os
import sys
from unittest.mock import MagicMock
import pytest
from hypothesis import settings

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "mock-anon-key")
os.environ.setdefault("JWT_SECRET", "test-secret-key-12345")

settings.register_profile("ci", max_examples=200, deadline=None)
settings.register_profile("dev", max_examples=50, deadline=None)
settings.load_profile("dev")

@pytest.fixture
def mock_db():
    from api import db
    original_client = getattr(db, "client", None)
    mock_client = MagicMock()
    # Por defecto, tokens desconocidos lanzan excepción en Supabase Auth
    mock_client.auth.get_user.side_effect = Exception("Invalid or expired token")
    db.client = mock_client
    yield mock_client
    db.client = original_client

@pytest.fixture
def client(mock_db):
    from fastapi.testclient import TestClient
    from api import app
    with TestClient(app) as test_client:
        yield test_client
