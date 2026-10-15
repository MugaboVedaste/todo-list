import re

import pytest

from app import create_app


@pytest.fixture
def db_path(tmp_path):
    """A throwaway database file, deleted by pytest after each test."""
    return str(tmp_path / "test_tasks.db")


@pytest.fixture
def app(db_path):
    # CSRF stays ON in tests so the real protection is exercised.
    return create_app({"TESTING": True, "DATABASE": db_path})


@pytest.fixture
def client(app):
    return app.test_client()


class Browser:
    """Wraps the test client and sends a valid CSRF token with every POST."""

    def __init__(self, client):
        self.client = client

    def get(self, url, **kwargs):
        return self.client.get(url, **kwargs)

    def token(self):
        page = self.client.get("/").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    def post(self, url, data=None, **kwargs):
        data = dict(data or {})
        data.setdefault("csrf_token", self.token())
        return self.client.post(url, data=data, **kwargs)


@pytest.fixture
def browser(client):
    return Browser(client)
