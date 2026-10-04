import time
from fastapi.testclient import TestClient
from tests.support import PUBLIC, start_login, finish_login


def wait(client, op):
    for _ in range(100):
        result = client.get('/api/v1/operations/' + op['id']).json()
        if result['status'] not in ('pending', 'running'):
            return result
        time.sleep(.02)
    raise AssertionError('operation did not finish')


def test_authenticated_backup_and_origin_check(authenticated_client):
    client = authenticated_client
    assert client.get('/health/live').status_code == 200
    assert client.get('/api/v1/status').status_code == 200
    assert client.patch('/api/v1/lights/bedroom/state', json={'power':False}, headers={'Origin':'https://untrusted.example'}).status_code == 403
    backup = client.get('/api/v1/backup')
    assert backup.status_code == 200 and 'attachment' in backup.headers['content-disposition']
    assert 'test-client-secret' not in backup.text and 'access-token' not in backup.text


def test_control_validation_and_scene_crud(authenticated_client):
    client = authenticated_client
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


def test_timer_api_persistence(pocket_factory):
    app,provider,_ = pocket_factory
    with TestClient(app,base_url=PUBLIC) as client:
        assert finish_login(client,start_login(client,provider)).status_code == 303
        url = '/api/v1/lights/bedroom/timer'
        assert client.put(url,json={'minutes':0}).status_code == 422
        assert client.put(url,json={'minutes':1441}).status_code == 422
        timer = client.put(url,json={'minutes':15}).json()
        assert timer['status'] == 'active'
    with TestClient(app,base_url=PUBLIC) as client:
        assert client.get('/api/v1/status').status_code == 401
        assert finish_login(client,start_login(client,provider)).status_code == 303
        restored = client.get('/api/v1/lights/bedroom').json()['timer']
        assert restored['due_at'] == timer['due_at']
        assert client.delete(url).status_code == 204
        assert client.get('/api/v1/lights/bedroom').json()['timer']['status'] == 'cancelled'


def test_frontend_root_assets_and_api_routes(pocket_client):
    import re
    client, _, _, _ = pocket_client
    response = client.get('/')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-cache'
    assert '/static/' not in response.text
    resources = re.findall(r'(?:src|href)="(/[^" ]+)"', response.text)
    assert any(resource.startswith('/assets/') for resource in resources)
    for resource in resources:
        assert client.get(resource).status_code == 200, resource
    manifest = client.get('/manifest.json').json()
    assert manifest['start_url'] == '/'
    assert manifest['icons'][0]['src'] == '/icon.svg'
    assert client.get('/api/v1/session').json()['authenticated'] is False
    assert client.get('/api/v1/status').status_code == 401
    assert client.get('/health/live').status_code == 200
    assert client.get('/src/main.ts').status_code == 404
    assert client.get('/static/icon.svg').status_code == 404
