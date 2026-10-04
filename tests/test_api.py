import time
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings, LightConfig


def application(tmp_path, **kwargs):
    settings = Settings(mode="demo", lights=[LightConfig(id="bedroom", name="房间吸顶灯", host="192.168.111.6")])
    return create_app(settings, tmp_path, access_token="test-token", **kwargs)


def wait(client, op):
    for _ in range(100):
        result = client.get('/api/v1/operations/' + op['id']).json()
        if result['status'] not in ('pending', 'running'):
            return result
        time.sleep(.02)
    raise AssertionError('operation did not finish')


def test_auth_login_cookie_origin_and_backup(tmp_path):
    with TestClient(application(tmp_path)) as client:
        assert client.get('/health/live').status_code == 200
        assert client.get('/api/v1/status').status_code == 401
        assert client.post('/api/v1/session', json={'token':'错误口令'}).status_code == 401
        assert client.post('/api/v1/session', json={'token':'test-token'}).status_code == 200
        assert client.cookies.get('opple_session')
        assert client.get('/api/v1/status').json()['mode'] == 'demo'
        assert client.patch('/api/v1/lights/bedroom/state', json={'power':False}, headers={'Origin':'https://untrusted.example'}).status_code == 403
        backup = client.get('/api/v1/backup')
        assert backup.status_code == 200 and 'attachment' in backup.headers['content-disposition']
        assert 'test-token' not in backup.text and 'access-token' not in backup.text
        assert client.delete('/api/v1/session').status_code == 200
        assert client.get('/api/v1/status').status_code == 401
        assert client.get('/api/v1/status', headers={'Authorization':'Bearer test-token'}).status_code == 200


def test_control_validation_and_scene_crud(tmp_path):
    with TestClient(application(tmp_path, open_demo=True)) as client:
        base = '/api/v1/lights/bedroom'
        for body in [{}, {'power':'off'}, {'brightness_percent':0}, {'color_temperature_kelvin':2900}, {'unknown':1}]:
            assert client.patch(base+'/state', json=body).status_code == 422
        assert client.get('/api/v1/lights/missing').status_code == 404
        response = client.patch(base+'/state', json={'power':False})
        assert response.status_code == 202
        assert wait(client, response.json())['status'] == 'confirmed'
        assert client.get(base).json()['state']['power'] is False
        response = client.patch(base+'/state', json={'color_temperature_kelvin':3200})
        assert wait(client, response.json())['status'] == 'staged'
        assert client.get(base).json()['state']['color_temperature_kelvin'] == 4000
        body = {'name':'睡前阅读','brightness_percent':25,'color_temperature_kelvin':3300,'icon':'book'}
        scene = client.post(base+'/scenes', json=body).json()
        body['name'] = '新的场景'
        assert client.put('/api/v1/scenes/'+scene['id'], json=body).status_code == 200
        op = client.post('/api/v1/scenes/'+scene['id']+'/apply').json()
        assert wait(client, op)['status'] == 'confirmed'
        state = client.get(base).json()['state']
        assert state['power'] is True and state['color_temperature_kelvin'] == 3300 and state['brightness_percent'] == 25
        assert client.delete('/api/v1/scenes/'+scene['id']).status_code == 204
        assert client.post('/api/v1/scenes/'+scene['id']+'/apply').status_code == 404
        assert client.get('/api/v1/events').json()


def test_timer_api_persistence(tmp_path):
    with TestClient(application(tmp_path, open_demo=True)) as client:
        url = '/api/v1/lights/bedroom/timer'
        assert client.put(url,json={'minutes':0}).status_code == 422
        assert client.put(url,json={'minutes':1441}).status_code == 422
        timer = client.put(url,json={'minutes':15}).json()
        assert timer['status'] == 'active'
    with TestClient(application(tmp_path, open_demo=True)) as client:
        restored = client.get('/api/v1/lights/bedroom').json()['timer']
        assert restored['due_at'] == timer['due_at']
        assert client.delete(url).status_code == 204
        assert client.get('/api/v1/lights/bedroom').json()['timer']['status'] == 'cancelled'


def test_demo_override_cannot_disable_real_auth(tmp_path):
    settings = Settings(mode="real", lights=[LightConfig(id="bedroom",name="test",host="127.0.0.1")])
    with TestClient(create_app(settings,tmp_path,access_token="test-token",open_demo=True)) as client:
        assert client.get('/api/v1/status').status_code == 401


def test_explicit_open_access_skips_login_and_keeps_origin_check(tmp_path, monkeypatch):
    monkeypatch.setenv("OPPLE_AUTH_DISABLED", "1")
    with TestClient(application(tmp_path)) as client:
        session = client.get('/api/v1/session').json()
        assert session['authenticated'] is True and session['auth_required'] is False
        assert client.get('/api/v1/status').status_code == 200
        assert client.post('/api/v1/lights/bedroom/refresh').status_code == 202
        assert client.patch('/api/v1/lights/bedroom/state', json={'power':False}, headers={'Origin':'https://untrusted.example'}).status_code == 403
        assert client.delete('/api/v1/session').status_code == 200
        assert client.get('/api/v1/status').status_code == 200
        assert not (tmp_path / 'access-token').exists()
