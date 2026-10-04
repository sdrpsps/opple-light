"""Test-only device and OIDC provider fakes; never imported by the service."""
import time
import json
from urllib.parse import parse_qs, urlsplit
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from app.auth import READ, CONTROL
from app.driver import Reading, DeviceUnavailable

class FakeDriver:
    def __init__(self, config):
        self.state = Reading(True, getattr(config, "default_brightness", 70), getattr(config, "default_kelvin", 4000))
        self.online = True

    def read(self):
        if not self.online:
            raise DeviceUnavailable("测试设备离线")
        return Reading(**vars(self.state))

    def write(self, target):
        self.read()
        time.sleep(.05)
        for key, value in target.items():
            setattr(self.state, key, value)
        return self.read()

    def close(self):
        pass

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


def start_login(client, provider):
    response = client.get('/auth/login',follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers['location']).query)
    provider.nonce = query['nonce'][0]
    return query


def finish_login(client, query):
    return client.get('/auth/callback',params={'state':query['state'][0],'code':'test-code','iss':ISSUER},follow_redirects=False)
