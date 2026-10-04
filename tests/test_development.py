import pytest
from fastapi.testclient import TestClient

from app.config import LightConfig, Settings
from app.main import create_app


def test_development_without_identity_service(tmp_path, monkeypatch):
    monkeypatch.setenv("OPPLE_ENV", "development")
    for key in ("OPPLE_OIDC_ISSUER", "OPPLE_PUBLIC_URL", "OPPLE_OIDC_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)

    def unexpected_auth(*args, **kwargs):
        raise AssertionError("Development must not initialize Pocket ID")

    monkeypatch.setattr("app.main.PocketAuth", unexpected_auth)
    settings = Settings(lights=[LightConfig(id="bedroom", name="测试灯", host="127.0.0.1")])
    with TestClient(create_app(settings, tmp_path), base_url="http://127.0.0.1:8080") as client:
        assert client.get('/api/v1/session').json() == {
            'authenticated': True, 'name': settings.name, 'login_enabled': False,
        }
        assert client.get('/api/v1/status').status_code == 200
        assert client.get('/api/v1/backup').status_code == 200
        url = '/api/v1/lights/bedroom/state'
        for origin in ('http://127.0.0.1:8080', 'http://127.0.0.1:5173',
                       'http://localhost:5173', 'http://localhost:5174', 'http://[::1]:5173'):
            assert client.patch(url, json={'power': False}, headers={'Origin': origin}).status_code == 202
            assert client.put('/api/v1/lights/bedroom/timer', json={'minutes': 15}, headers={'Origin': origin}).status_code == 200
        for origin in ('https://untrusted.example', 'http://localhost.evil.example:5173',
                       'http://localhost@untrusted.example:5173'):
            assert client.patch(url, json={'power': False}, headers={'Origin': origin}).status_code == 403
        assert client.delete('/api/v1/session').json()['authenticated'] is True
        assert client.get('/auth/login').status_code == 404
        assert client.app.state.pocket is None
    assert not (tmp_path / 'auth.db').exists()


@pytest.mark.parametrize('environment', ['', 'production', 'developmnt'])
def test_other_environments_require_authentication(environment, pocket_factory, monkeypatch):
    _, provider, path = pocket_factory
    monkeypatch.setenv('OPPLE_ENV', environment)
    settings = Settings(lights=[LightConfig(id="bedroom", name="测试灯", host="127.0.0.1")])
    with TestClient(create_app(settings, path)) as client:
        assert client.get('/api/v1/session').json()['login_enabled'] is True
        assert client.get('/api/v1/status').status_code == 401
        assert client.patch('/api/v1/lights/bedroom/state', json={'power': False},
                            headers={'Origin': 'http://localhost:5173'}).status_code == 403
    assert provider.requests
