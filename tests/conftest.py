import httpx
import pytest
from fastapi.testclient import TestClient
from app.auth import PocketAuth
from app.config import LightConfig, Settings
from app.main import create_app
from tests.support import FakeDriver, Provider, ISSUER, PUBLIC, CLIENT, start_login, finish_login


@pytest.fixture(autouse=True)
def isolated_lights(monkeypatch):
    # Never create physical lamp sockets through the service in application tests.
    # The protocol test uses app.driver.OppleDriver directly against local UDP.
    monkeypatch.setattr("app.service.OppleDriver", FakeDriver)


@pytest.fixture
def pocket_factory(tmp_path, monkeypatch):
    for key,value in {
        "OPPLE_OIDC_ISSUER":ISSUER, "OPPLE_PUBLIC_URL":PUBLIC,
        "OPPLE_OIDC_CLIENT_ID":CLIENT, "OPPLE_OIDC_CLIENT_SECRET":"test-client-secret",
        # Legacy flags and credentials must have no effect.
        "OPPLE_AUTH_MODE":"open", "OPPLE_AUTH_DISABLED":"1", "OPPLE_TOKEN":"old-token",
        "OPPLE_MODE":"demo", "OPPLE_DEMO_OPEN":"1",
    }.items():
        monkeypatch.setenv(key,value)
    provider = Provider()
    original = PocketAuth.__init__
    monkeypatch.setattr(PocketAuth, "__init__", lambda self,config: original(self,config,httpx.AsyncClient(transport=httpx.MockTransport(provider.handle))))
    settings = Settings(lights=[LightConfig(id="bedroom",name="测试灯",host="127.0.0.1")])
    return create_app(settings,tmp_path), provider, tmp_path


@pytest.fixture
def pocket_client(pocket_factory):
    app,provider,path = pocket_factory
    with TestClient(app,base_url=PUBLIC) as client:
        yield client,provider,app,path


@pytest.fixture
def authenticated_client(pocket_client):
    client,provider,_,_ = pocket_client
    assert finish_login(client,start_login(client,provider)).status_code == 303
    return client
