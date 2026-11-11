import pytest

from homelimiter.adapters import MockAdapter
from homelimiter.api import create_app
from homelimiter.service import Service
from homelimiter.store import Store


@pytest.fixture
def service(tmp_path):
    result = Service(Store(tmp_path / "test.db"), MockAdapter())
    result.refresh()
    return result


@pytest.fixture
def client(service, tmp_path):
    from fastapi.testclient import TestClient

    app = create_app(tmp_path, service=service, token="x" * 43, background=False)
    with TestClient(app, headers={"Authorization": "Bearer " + "x" * 43}) as client:
        yield client
