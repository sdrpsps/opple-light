import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import CONTROL, READ, PocketAuth, SESSION_COOKIE, STATE_COOKIE
from app.config import LightConfig, Settings
from app.main import create_app

ISSUER = "https://auth.example.com"
PUBLIC = "https://light.example.com"
RESOURCE = PUBLIC + "/api"
CLIENT = "web-client"


class Provider:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.kid = "test-key"
        self.nonce = ""
        self.bad_nonce = False
        self.identity_changes = {}
        self.scopes = f"{READ} {CONTROL}"
        self.requests = []

    def token(self, **changes):
        claims = {"iss":ISSUER,"aud":RESOURCE,"sub":"user-1","iat":int(time.time()),"exp":int(time.time())+3600,"scope":self.scopes}
        claims.update(changes)
        return jwt.encode(claims,self.key,algorithm="RS256",headers={"kid":self.kid})

    def handle(self, request):
        self.requests.append(request)
        if request.url.path == '/.well-known/openid-configuration':
            return httpx.Response(200,json={"issuer":ISSUER,"authorization_endpoint":ISSUER+'/authorize',"token_endpoint":ISSUER+'/api/oidc/token',"jwks_uri":ISSUER+'/.well-known/jwks.json',"code_challenge_methods_supported":["S256"]})
        if request.url.path == '/.well-known/jwks.json':
            key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
            key.update(kid=self.kid,alg="RS256",use="sig")
            return httpx.Response(200,json={"keys":[key]})
        if request.url.path == '/api/oidc/token':
            identity = dict(aud=CLIENT,nonce='wrong' if self.bad_nonce else self.nonce,name='测试用户')
            identity.update(self.identity_changes)
            return httpx.Response(200,json={"access_token":self.token(),"id_token":self.token(**identity)})
        return httpx.Response(404)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for key,value in {"OPPLE_AUTH_MODE":"pocketid","OPPLE_AUTH_DISABLED":"1","OPPLE_OIDC_ISSUER":ISSUER,
                      "OPPLE_PUBLIC_URL":PUBLIC,"OPPLE_OIDC_CLIENT_ID":CLIENT,"OPPLE_OIDC_CLIENT_SECRET":"test-client-secret"}.items():
        monkeypatch.setenv(key,value)
    provider = Provider()
    original = PocketAuth.__init__
    monkeypatch.setattr(PocketAuth,'__init__',lambda self,config: original(self,config,httpx.AsyncClient(transport=httpx.MockTransport(provider.handle))))
    settings = Settings(mode='demo',lights=[LightConfig(id='bedroom',name='测试灯',host='127.0.0.1')])
    app = create_app(settings,tmp_path,open_demo=True,access_token='old-token')
    with TestClient(app,base_url=PUBLIC) as client:
        yield client,provider,app,tmp_path


def headers(provider, **changes):
    return {'Authorization':'Bearer '+provider.token(**changes)}


def start_login(client, provider):
    response = client.get('/auth/login',follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers['location']).query)
    provider.nonce = query['nonce'][0]
    return query


def finish_login(client, query):
    return client.get('/auth/callback',params={'state':query['state'][0],'code':'test-code','iss':ISSUER},follow_redirects=False)


def test_pocket_mode_overrides_open_demo_and_old_credentials(setup):
    client,provider,app,path = setup
    info = client.get('/api/v1/session').json()
    assert info['auth_mode']=='pocketid' and info['authenticated'] is False
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
    settings=Settings(mode='demo',lights=[LightConfig(id='bedroom',name='测试',host='127.0.0.1')])
    with pytest.raises(ValueError):create_app(settings,tmp_path)
