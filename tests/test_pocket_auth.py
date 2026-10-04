import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import CONTROL, READ, SESSION_COOKIE
from app.config import LightConfig, Settings
from app.main import create_app

from tests.support import ISSUER, PUBLIC, RESOURCE, CLIENT, start_login, finish_login

@pytest.fixture
def setup(pocket_client):
    return pocket_client


def headers(provider, **changes):
    return {'Authorization':'Bearer '+provider.token(**changes)}


def test_old_flags_and_credentials_cannot_disable_pocket_id(setup):
    client,provider,app,path = setup
    info = client.get('/api/v1/session').json()
    assert info['authenticated'] is False
    assert client.post('/api/v1/session',json={'token':'old-token'}).status_code == 405
    assert client.get('/api/v1/status').status_code == 401
    assert client.get('/api/v1/status',headers={'Authorization':'Bearer old-token'}).status_code == 401
    assert client.get('/api/v1/status',headers={'X-API-KEY':'pocket-admin-key'}).status_code == 401
    assert not (path/'access-token').exists()


def test_api_scopes_and_cached_verification(setup):
    client,provider,app,_ = setup
    read = headers(provider,sub='client-shortcuts',scope=READ)
    assert client.get('/api/v1/status',headers=read).status_code == 200
    assert client.post('/api/v1/lights/bedroom/refresh',headers=read).status_code == 403
    both = headers(provider,sub='client-shortcuts')
    assert client.post('/api/v1/lights/bedroom/refresh',headers=both).status_code == 202
    assert client.patch('/api/v1/lights/bedroom/state',headers=both,json={'power':False}).status_code == 202
    assert len(provider.requests)==2, 'API verification must not call Pocket ID for every request'


@pytest.mark.parametrize('changes',[{'iss':'https://wrong.example.com'},{'aud':'another-api'},{'exp':int(time.time())-100},{'iat':int(time.time())+3600},{'scope':['lights:read']}])
def test_invalid_token_claims_are_rejected(setup,changes):
    client,provider,_,_ = setup
    assert client.get('/api/v1/status',headers=headers(provider,**changes)).status_code == 401


def test_id_token_forgery_and_unsigned_tokens_are_rejected(setup):
    client,provider,_,_ = setup
    assert client.get('/api/v1/status',headers=headers(provider,aud=CLIENT)).status_code == 401
    for token in [jwt.encode({'iss':ISSUER,'aud':RESOURCE,'sub':'attacker','exp':int(time.time())+3600},'attacker-secret',algorithm='HS256'), provider.token()[:-3]+'xxx']:
        assert client.get('/api/v1/status',headers={'Authorization':'Bearer '+token}).status_code == 401


def test_oidc_pkce_session_logout_and_replay(setup):
    client,provider,app,path = setup
    query = start_login(client,provider)
    assert query['resource']==[RESOURCE] and query['code_challenge_method']==['S256']
    assert set(query['scope'][0].split())=={'openid','profile',READ,CONTROL}
    state=query['state'][0]
    transaction=app.state.pocket.store.get(state,'login')
    challenge=base64.urlsafe_b64encode(hashlib.sha256(transaction['verifier'].encode()).digest()).rstrip(b'=').decode()
    assert query['code_challenge']==[challenge]
    result=finish_login(client,query)
    assert result.status_code==303 and result.headers['location']==PUBLIC+'/'
    assert result.headers['referrer-policy']=='no-referrer'
    assert result.headers['cache-control']=='no-store'
    assert client.get('/api/v1/status').status_code==200
    assert 'Secure' in result.headers['set-cookie'] and 'HttpOnly' in result.headers['set-cookie']
    session=client.cookies.get(SESSION_COOKIE)
    exchange=provider.requests[-1]
    assert parse_qs(exchange.content.decode())['code_verifier']==[transaction['verifier']]
    assert exchange.headers['authorization'].startswith('Basic ')
    assert not app.state.pocket.store.get(state,'login')
    assert finish_login(client,query).status_code==400
    assert client.get('/api/v1/status',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.delete('/api/v1/session').status_code==200
    assert not app.state.pocket.store.get(session,'session')
    assert client.get('/api/v1/status').status_code==401
    # Neither bearer tokens nor client secrets belong in the session database.
    stored=path.joinpath('auth.db').read_bytes()
    assert b'test-client-secret' not in stored
    assert provider.token().encode() not in stored


def test_login_state_and_nonce_validation(setup):
    client,provider,app,_ = setup
    query=start_login(client,provider)
    assert client.get('/auth/callback',params={'state':'wrong','code':'test'},follow_redirects=False).status_code==400
    provider.bad_nonce=True
    assert finish_login(client,query).status_code==400
    assert client.get('/api/v1/status').status_code==401
    assert not app.state.pocket.store.get(query['state'][0],'login')


@pytest.mark.parametrize('changes', [
    {'aud':[CLIENT,'another-client']},
    {'azp':'another-client'},
    {'at_hash':'wrong-access-token-hash'},
])
def test_identity_token_client_and_access_binding(setup, changes):
    client,provider,app,_ = setup
    provider.identity_changes = changes
    query = start_login(client,provider)
    assert finish_login(client,query).status_code == 400
    assert client.get('/api/v1/status').status_code == 401


def test_cookie_expiry_and_origin_check(setup):
    client,provider,app,_ = setup
    query=start_login(client,provider);assert finish_login(client,query).status_code==303
    assert client.patch('/api/v1/lights/bedroom/state',json={'power':False},headers={'Origin':'https://attacker.example.com'}).status_code==403
    session=client.cookies.get(SESSION_COOKIE)
    app.state.pocket.store.db.execute('UPDATE auth_records SET expires=?',(time.time()-1,));app.state.pocket.store.db.commit()
    assert client.get('/api/v1/status').status_code==401
    assert app.state.pocket.store.get(session,'session') is None


def test_signing_key_rotation(setup):
    client,provider,app,_ = setup
    provider.key=rsa.generate_private_key(public_exponent=65537,key_size=2048);provider.kid='rotated-key'
    app.state.pocket.last_fetch=0
    assert client.get('/api/v1/status',headers=headers(provider)).status_code==200
    assert len(provider.requests)==3


def test_incomplete_config_fails_closed(monkeypatch,tmp_path):
    monkeypatch.setenv('OPPLE_AUTH_MODE','pocketid');monkeypatch.setenv('OPPLE_AUTH_DISABLED','1')
    monkeypatch.delenv('OPPLE_OIDC_ISSUER',raising=False)
    settings=Settings(lights=[LightConfig(id='bedroom',name='测试',host='127.0.0.1')])
    with pytest.raises(ValueError):
        with TestClient(create_app(settings,tmp_path)):
            pass
