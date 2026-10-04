"""Pocket ID OIDC and scoped API access; no local accounts or roles."""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

READ = "lights:read"
CONTROL = "lights:control"
SESSION_COOKIE = "opple_oidc_session"
STATE_COOKIE = "opple_oidc_state"


def secret_setting(name):
    path = os.getenv(name + "_FILE")
    return Path(path).read_text().strip() if path else os.getenv(name, "").strip()


def https_url(value, label, origin_only=False):
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.netloc or parts.username or parts.password
            or parts.query or parts.fragment or (origin_only and parts.path not in ("", "/"))):
        raise ValueError(f"{label} 必须是有效的 HTTPS 地址" + ("，使用独立域名" if origin_only else ""))
    return value.rstrip("/")


@dataclass(frozen=True)
class PocketConfig:
    issuer: str
    public_url: str
    client_id: str
    client_secret: str
    resource: str

    @classmethod
    def from_env(cls):
        issuer = https_url(os.getenv("OPPLE_OIDC_ISSUER", ""), "OPPLE_OIDC_ISSUER")
        public = https_url(os.getenv("OPPLE_PUBLIC_URL", ""), "OPPLE_PUBLIC_URL", origin_only=True)
        client = os.getenv("OPPLE_OIDC_CLIENT_ID", "").strip()
        secret = secret_setting("OPPLE_OIDC_CLIENT_SECRET")
        resource = https_url(os.getenv("OPPLE_OIDC_RESOURCE") or public + "/api", "OPPLE_OIDC_RESOURCE")
        if not client:
            raise ValueError("Pocket ID 需要 OPPLE_OIDC_CLIENT_ID；公共客户端无需 Client Secret")
        return cls(issuer, public, client, secret, resource)


class AuthStore:
    """Only temporary login transactions and revocable, opaque sessions."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self.db.execute("CREATE TABLE IF NOT EXISTS auth_records (key TEXT PRIMARY KEY, kind TEXT NOT NULL, expires REAL NOT NULL, body TEXT NOT NULL)")
        self.db.commit()

    def put(self, token, kind, expires, body):
        self.db.execute("DELETE FROM auth_records WHERE expires <= ?", (time.time(),))
        self.db.execute("INSERT INTO auth_records VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), kind, expires, json.dumps(body)))
        self.db.commit()

    def get(self, token, kind, consume=False):
        key = hashlib.sha256(token.encode()).hexdigest()
        row = self.db.execute("SELECT expires,body FROM auth_records WHERE key=? AND kind=?", (key,kind)).fetchone()
        if consume:
            self.delete(token)
        if not row or row[0] <= time.time():
            return None
        return json.loads(row[1])

    def delete(self, token):
        self.db.execute("DELETE FROM auth_records WHERE key=?", (hashlib.sha256(token.encode()).hexdigest(),))
        self.db.commit()

    def close(self):
        self.db.close()


class PocketAuth:
    def __init__(self, config, client=None):
        self.config = config
        self.client = client or httpx.AsyncClient(timeout=8, follow_redirects=False)
        self.store = None
        self.metadata = {}
        self.keys = {}
        self.key_time = 0
        self.last_fetch = 0
        self.lock = asyncio.Lock()

    def trusted_endpoint(self, url):
        https_url(url, "Pocket ID 元数据端点")
        if urlsplit(url).netloc != urlsplit(self.config.issuer).netloc:
            raise ValueError("Pocket ID 元数据端点必须使用配置的身份服务域名")
        return url

    async def start(self, directory):
        try:
            response = await self.client.get(self.config.issuer + "/.well-known/openid-configuration")
            response.raise_for_status()
            self.metadata = response.json()
            if self.metadata.get("issuer") != self.config.issuer:
                raise ValueError("Pocket ID issuer 与配置不一致")
            for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                self.trusted_endpoint(self.metadata[name])
            if "S256" not in self.metadata.get("code_challenge_methods_supported", []):
                raise ValueError("身份服务必须支持 PKCE S256")
            await self.load_keys()
            self.store = AuthStore(directory / "auth.db")
        except Exception:
            await self.client.aclose()
            raise

    async def load_keys(self):
        self.last_fetch = time.monotonic()
        response = await self.client.get(self.metadata["jwks_uri"])
        response.raise_for_status()
        if len(response.content) > 100_000:
            raise ValueError("Pocket ID 公钥响应过大")
        keys = response.json().get("keys", [])
        self.keys = {item["kid"]: jwt.PyJWK.from_dict(item).key for item in keys
                     if item.get("kid") and item.get("kty") == "RSA" and item.get("use", "sig") == "sig"
                     and item.get("alg", "RS256") == "RS256"}
        if not self.keys:
            raise ValueError("Pocket ID 未提供 RS256 验签公钥")
        self.key_time = time.monotonic()

    async def claims(self, token, audience):
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise ValueError("unsupported token")
            kid = header["kid"]
            async with self.lock:
                if time.monotonic() - self.key_time > 300 or (kid not in self.keys and time.monotonic() - self.last_fetch > 10):
                    await self.load_keys()
                key = self.keys.get(kid)
            if key is None:
                raise ValueError("unknown signing key")
            return jwt.decode(token, key, algorithms=["RS256"], audience=audience, issuer=self.config.issuer,
                              options={"require": ["iss", "aud", "exp", "iat", "sub"]}, leeway=10)
        except (jwt.PyJWTError, ValueError, KeyError, TypeError):
            raise HTTPException(401, "访问令牌无效或已过期") from None
        except httpx.HTTPError:
            raise HTTPException(503, "身份服务暂时无法连接，请稍后再试") from None

    async def principal(self, request):
        # An invalid explicit credential never falls back to a browser cookie.
        authorization = request.headers.get("authorization")
        if authorization:
            if not authorization.startswith("Bearer ") or len(authorization) > 16384:
                raise HTTPException(401, "请提供有效的 Bearer 访问令牌")
            claims = await self.claims(authorization[7:], self.config.resource)
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                raise HTTPException(401, "访问令牌权限格式无效")
            return {"sub": claims["sub"], "scopes": scope.split(), "name": "API 客户端"}
        token = request.cookies.get(SESSION_COOKIE, "")
        return self.store.get(token, "session") if token else None

    async def authorize(self, request, scope):
        principal = await self.principal(request)
        if not principal:
            raise HTTPException(401, "请通过 Pocket ID 登录")
        if scope not in principal["scopes"]:
            raise HTTPException(403, "此凭证没有执行该操作的权限")
        return principal

    async def login(self):
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.store.put(state, "login", time.time() + 600, {"nonce":nonce,"verifier":verifier})
        query = urlencode({"response_type":"code", "client_id":self.config.client_id,
                           "redirect_uri":self.config.public_url + "/auth/callback", "state":state, "nonce":nonce,
                           "code_challenge":challenge, "code_challenge_method":"S256",
                           "scope":"openid profile"})
        response = RedirectResponse(self.metadata["authorization_endpoint"] + "?" + query, status_code=302)
        response.set_cookie(STATE_COOKIE,state,max_age=600,httponly=True,secure=True,samesite="lax",path="/auth")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def callback(self, request):
        state = request.query_params.get("state", "")
        cookie = request.cookies.get(STATE_COOKIE, "")
        if not state or not cookie or not secrets.compare_digest(state,cookie):
            raise HTTPException(400, "登录请求不匹配，请重新登录")
        transaction = self.store.get(state, "login", consume=True)
        if not transaction:
            raise HTTPException(400, "登录请求已过期或已经使用，请重新登录")
        error = request.query_params.get("error")
        if error:
            messages = {
                "access_denied": "Pocket ID 拒绝了登录，请确认你的账户允许访问一室光，或重新授权。",
                "invalid_request": "Pocket ID 拒绝了登录参数，请检查客户端设置和回调地址。",
                "invalid_scope": "Pocket ID 不支持请求的登录权限，请检查客户端设置。",
                "invalid_target": "Pocket ID 未授权请求的 API 资源，请检查客户端的 API access 设置。",
            }
            raise HTTPException(400, messages.get(error, "Pocket ID 未完成授权，请重新登录。"))
        if not request.query_params.get("code"):
            raise HTTPException(400, "Pocket ID 未返回登录授权码，请重新登录")
        if request.query_params.get("iss", self.config.issuer) != self.config.issuer:
            raise HTTPException(400, "登录响应来源不匹配")
        try:
            data = {"grant_type":"authorization_code", "code":request.query_params["code"],
                    "redirect_uri":self.config.public_url + "/auth/callback", "code_verifier":transaction["verifier"]}
            auth = None
            if self.config.client_secret:
                auth = httpx.BasicAuth(self.config.client_id, self.config.client_secret)
            else:
                data["client_id"] = self.config.client_id
            response = await self.client.post(self.metadata["token_endpoint"], auth=auth, data=data)
            response.raise_for_status()
            token = response.json()
            identity = await self.claims(token["id_token"],self.config.client_id)
            audiences = identity["aud"]
            if (isinstance(audiences, list) and len(audiences) > 1 and "azp" not in identity
                    or "azp" in identity and identity["azp"] != self.config.client_id):
                raise HTTPException(400, "登录客户端不匹配")
            if not secrets.compare_digest(str(identity.get("nonce", "")),transaction["nonce"]):
                raise HTTPException(400, "登录校验失败，请重新登录")
            if "at_hash" in identity:
                digest = hashlib.sha256(token["access_token"].encode()).digest()
                expected = base64.urlsafe_b64encode(digest[:len(digest)//2]).rstrip(b"=").decode()
                if not isinstance(identity["at_hash"], str) or not secrets.compare_digest(identity["at_hash"], expected):
                    raise HTTPException(400, "登录访问令牌不匹配")
            # Browser access is granted by the OIDC client's allowed users/groups.
            # API-resource tokens are independent and remain strictly scoped.
            expiry = min(time.time() + 8*3600, identity["exp"])
            session = secrets.token_urlsafe(32)
            self.store.put(session,"session",expiry,{"sub":identity["sub"],"scopes":[READ, CONTROL],
                           "name":str(identity.get("name") or identity.get("preferred_username") or "已登录")[:100]})
            old = request.cookies.get(SESSION_COOKIE)
            if old: self.store.delete(old)
            result = RedirectResponse(self.config.public_url + "/",status_code=303)
            result.set_cookie(SESSION_COOKIE,session,max_age=max(1,int(expiry-time.time())),httponly=True,secure=True,samesite="lax",path="/")
            result.delete_cookie(STATE_COOKIE,path="/auth",secure=True,samesite="lax")
            result.headers["Cache-Control"] = "no-store"
            result.headers["Referrer-Policy"] = "no-referrer"
            return result
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise HTTPException(502, "Pocket ID 登录未完成，请检查客户端配置后重试") from None

    def logout(self, request, response):
        token = request.cookies.get(SESSION_COOKIE)
        if token: self.store.delete(token)
        response.delete_cookie(SESSION_COOKIE,path="/",secure=True,samesite="lax")

    async def close(self):
        if self.store: self.store.close()
        await self.client.aclose()
