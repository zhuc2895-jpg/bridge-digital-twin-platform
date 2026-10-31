import pytest
from fastapi.testclient import TestClient

from app.dependencies import create_services
from app.main import create_app


@pytest.fixture
def app():
    services = create_services()
    services.live_stream_autostart = False
    return create_app(services)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
