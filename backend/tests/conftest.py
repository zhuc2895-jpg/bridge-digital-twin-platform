import pytest
from fastapi.testclient import TestClient

from tests.helpers import create_live_app


@pytest.fixture
def app():
    _, application = create_live_app()
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
