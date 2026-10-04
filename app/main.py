import hashlib
import hmac
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from .config import load_settings
from .service import LightService
from .storage import Storage

VERSION = "1.0.0"
STATIC = Path(__file__).parent / "static"
log = logging.getLogger(__name__)


class StatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    power: StrictBool | None = None
    color_temperature_kelvin: int | None = Field(default=None, ge=2700, le=6500)
    brightness_percent: int | None = Field(default=None, ge=1, le=100)


class SceneBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=20)
    color_temperature_kelvin: int = Field(ge=2700, le=6500)
    brightness_percent: int = Field(ge=1, le=100)
    icon: str = Field(default="spark", pattern="^(sun|book|moon|spark)$")


class TimerBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    minutes: int = Field(ge=1, le=1440)


class LoginBody(BaseModel):
    token: str = Field(min_length=1, max_length=300)


def create_app(settings=None, data_dir=None, access_token=None, open_demo=False):
    settings = settings or load_settings()
    data_dir = Path(data_dir or os.getenv("OPPLE_DATA", "data"))
    open_demo = (open_demo or os.getenv("OPPLE_DEMO_OPEN") == "1") and settings.mode == "demo"

    auth_required = not (open_demo or os.getenv("OPPLE_AUTH_DISABLED") == "1")

    @asynccontextmanager
    async def lifespan(app):
        data_dir.mkdir(parents=True, exist_ok=True)
        token = (access_token or os.getenv("OPPLE_TOKEN")) if auth_required else ""
        if auth_required and not token:
            path = data_dir / "access-token"
            if path.exists():
                token = path.read_text().strip()
                if not token:
                    raise RuntimeError("access-token 文件为空，请删除空文件或设置 OPPLE_TOKEN")
            else:
                token = secrets.token_urlsafe(24)
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as file:
                    file.write(token + "\n")
                log.info("访问口令已生成，保存在数据目录的 access-token 文件中")
        app.state.token = token
        app.state.cookie = hmac.new(token.encode(), b"opple-session-v1", hashlib.sha256).hexdigest()
        app.state.login_attempts = {}
        app.state.storage = Storage(data_dir / "service.db")
        app.state.service = LightService(settings, app.state.storage)
        await app.state.service.start()
        try:
            yield
        finally:
            await app.state.service.stop()
            app.state.storage.close()

    app = FastAPI(title="一室光 · OPPLE 本地控制", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)

    def authenticated(request):
        if not auth_required:
            return True
        bearer = request.headers.get("authorization", "")
        return (bearer.startswith("Bearer ") and secrets.compare_digest(bearer[7:].encode(), request.app.state.token.encode())) or secrets.compare_digest(request.cookies.get("opple_session", "").encode(), request.app.state.cookie.encode())

    @app.middleware("http")
    async def access(request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and urlsplit(origin).netloc != request.headers.get("host"):
                    return JSONResponse({"detail": "请从本服务页面发起操作"}, status_code=403)
            if request.url.path not in ("/api/v1/session",) and not authenticated(request):
                return JSONResponse({"detail": "请先输入访问口令"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def light(light_id):
        controller = app.state.service.lights.get(light_id)
        if controller is None:
            raise HTTPException(404, "没有找到这盏灯")
        return controller

    def submit(controller, target, source="manual"):
        try:
            return controller.submit(target, source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except OverflowError as exc:
            raise HTTPException(429, str(exc)) from exc

    @app.get("/health/live")
    async def health():
        return {"status": "ok", "version": VERSION}

    @app.get("/api/v1/session")
    async def session(request: Request):
        return {"authenticated": bool(authenticated(request)), "mode": settings.mode, "name": settings.name, "auth_required": auth_required}

    @app.post("/api/v1/session")
    async def login(body: LoginBody, request: Request, response: Response):
        if not auth_required:
            return {"authenticated": True}
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        attempts = app.state.login_attempts
        if len(attempts) > 500:
            attempts.clear()
        recent = [stamp for stamp in attempts.get(ip, []) if now - stamp < 60]
        if len(recent) >= 10:
            raise HTTPException(429, "尝试次数较多，请一分钟后再试")
        if not secrets.compare_digest(body.token.encode(), app.state.token.encode()):
            attempts[ip] = [*recent, now]
            raise HTTPException(401, "访问口令不正确")
        attempts.pop(ip, None)
        response.set_cookie("opple_session", app.state.cookie, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=14*24*3600)
        return {"authenticated": True}

    @app.delete("/api/v1/session")
    async def logout(response: Response):
        response.delete_cookie("opple_session")
        return {"authenticated": False}

    @app.get("/api/v1/status")
    async def status():
        return {"name": settings.name, "version": VERSION, "mode": settings.mode, "server_time": time.time(), "timezone": settings.timezone,
                "lights": [controller.view() for controller in app.state.service.lights.values()]}

    @app.get("/api/v1/lights")
    async def lights():
        return [controller.view() for controller in app.state.service.lights.values()]

    @app.get("/api/v1/lights/{light_id}")
    async def get_light(light_id: str):
        return light(light_id).view()

    @app.patch("/api/v1/lights/{light_id}/state", status_code=202)
    async def set_light(light_id: str, body: StatePatch):
        return submit(light(light_id), body.model_dump(exclude_none=True))

    @app.post("/api/v1/lights/{light_id}/refresh", status_code=202)
    async def refresh(light_id: str):
        light(light_id).refresh()
        return {"message": "已请求刷新"}

    @app.get("/api/v1/operations/{operation_id}")
    async def operation(operation_id: str):
        op = app.state.storage.get("operations", operation_id)
        if not op:
            raise HTTPException(404, "操作记录不存在或已清理")
        return op

    @app.get("/api/v1/scenes")
    async def scenes():
        return app.state.storage.all("scenes")

    @app.post("/api/v1/lights/{light_id}/scenes", status_code=201)
    async def create_scene(light_id: str, body: SceneBody):
        controller = light(light_id)
        try:
            controller.validate_target({"color_temperature_kelvin": body.color_temperature_kelvin})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if len([scene for scene in app.state.storage.all("scenes") if scene["light_id"] == light_id]) >= 12:
            raise HTTPException(422, "每盏灯最多保存 12 个场景")
        scene = {**body.model_dump(), "id": uuid4().hex, "light_id": light_id}
        app.state.storage.put("scenes", scene["id"], scene)
        return scene

    def scene_by_id(scene_id):
        scene = app.state.storage.get("scenes", scene_id)
        if scene is None:
            raise HTTPException(404, "场景不存在")
        return scene

    @app.put("/api/v1/scenes/{scene_id}")
    async def update_scene(scene_id: str, body: SceneBody):
        scene = scene_by_id(scene_id)
        try:
            light(scene["light_id"]).validate_target({"color_temperature_kelvin": body.color_temperature_kelvin})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        scene.update(body.model_dump())
        app.state.storage.put("scenes", scene_id, scene)
        return scene

    @app.delete("/api/v1/scenes/{scene_id}", status_code=204)
    async def delete_scene(scene_id: str):
        scene_by_id(scene_id)
        app.state.storage.delete("scenes", scene_id)
        return Response(status_code=204)

    @app.post("/api/v1/scenes/{scene_id}/apply", status_code=202)
    async def apply_scene(scene_id: str):
        scene = scene_by_id(scene_id)
        return submit(light(scene["light_id"]), {"power": True, "color_temperature_kelvin": scene["color_temperature_kelvin"], "brightness_percent": scene["brightness_percent"]}, "scene")

    @app.put("/api/v1/lights/{light_id}/timer")
    async def set_timer(light_id: str, body: TimerBody):
        light(light_id)
        return app.state.service.set_timer(light_id, body.minutes)

    @app.delete("/api/v1/lights/{light_id}/timer", status_code=204)
    async def cancel_timer(light_id: str):
        light(light_id)
        app.state.service.cancel_timer(light_id)
        return Response(status_code=204)

    @app.get("/api/v1/events")
    async def events():
        return app.state.storage.events()

    @app.get("/api/v1/backup")
    async def backup():
        value = {"format_version": 1, "config": settings.model_dump(mode="json"), "scenes": app.state.storage.all("scenes"),
                 "preferences": {key: app.state.storage.get("preferences", key) or {} for key in app.state.service.lights}}
        return JSONResponse(value, headers={"Content-Disposition": 'attachment; filename="opple-backup.json"'})

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
