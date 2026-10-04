import os
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
from .auth import CONTROL, READ, PocketAuth, PocketConfig

VERSION = "1.0.0"
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


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


def create_app(settings=None, data_dir=None):
    settings = settings or load_settings()
    data_dir = Path(data_dir or os.getenv("OPPLE_DATA", "data"))
    development = os.getenv("OPPLE_ENV") == "development"
    pocket = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal pocket
        data_dir.mkdir(parents=True, exist_ok=True)
        if not development:
            pocket = PocketAuth(PocketConfig.from_env())
            await pocket.start(data_dir)
        app.state.pocket = pocket
        app.state.storage = Storage(data_dir / "service.db")
        app.state.service = LightService(settings, app.state.storage)
        try:
            await app.state.service.start()
            yield
        finally:
            await app.state.service.stop()
            app.state.storage.close()
            if pocket:
                await pocket.close()

    app = FastAPI(title="一室光 · OPPLE 本地控制", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)

    async def authenticated(request):
        if development:
            return True
        if pocket:
            try:
                return bool(await pocket.principal(request))
            except HTTPException:
                return False
        return False

    @app.middleware("http")
    async def access(request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                allowed_origin = pocket.config.public_url if pocket else None
                local_development_origin = False
                if development and origin:
                    try:
                        parsed_origin = urlsplit(origin)
                        local_development_origin = (
                            parsed_origin.scheme in ("http", "https")
                            and parsed_origin.hostname in ("localhost", "127.0.0.1", "::1")
                            and not parsed_origin.username and not parsed_origin.password
                        )
                    except ValueError:
                        pass
                if origin and not local_development_origin and ((allowed_origin and origin != allowed_origin) or
                               (not allowed_origin and urlsplit(origin).netloc != request.headers.get("host"))):
                    return JSONResponse({"detail": "请从本服务页面发起操作"}, status_code=403)
            if request.url.path != "/api/v1/session" and not development:
                try:
                    request.state.principal = await pocket.authorize(request, READ if request.method in ("GET", "HEAD", "OPTIONS") else CONTROL)
                except HTTPException as exc:
                    return JSONResponse({"detail":exc.detail},status_code=exc.status_code,
                                        headers={"Cache-Control":"no-store", **({"WWW-Authenticate":"Bearer"} if exc.status_code == 401 else {})})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer" if request.url.path.startswith("/auth/") else "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"
        if request.url.path.startswith(("/api/", "/auth/")):
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

    @app.get("/auth/login")
    async def oidc_login():
        if not pocket:
            raise HTTPException(404, "未启用 Pocket ID")
        return await pocket.login()

    @app.get("/auth/callback")
    async def oidc_callback(request: Request):
        if not pocket:
            raise HTTPException(404, "未启用 Pocket ID")
        try:
            return await pocket.callback(request)
        except HTTPException as exc:
            # Vue renders the error page; never embed callback parameters in HTML.
            response = FileResponse(FRONTEND_DIST / "index.html", status_code=exc.status_code,
                                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
            pending = request.cookies.get("opple_oidc_state")
            if pending:
                pocket.store.delete(pending)
            response.delete_cookie("opple_oidc_state", path="/auth", secure=True, samesite="lax")
            return response

    @app.get("/health/live")
    async def health():
        return {"status": "ok", "version": VERSION}

    @app.get("/api/v1/session")
    async def session(request: Request):
        return {"authenticated": await authenticated(request), "name": settings.name,
                "login_enabled": not development}

    @app.delete("/api/v1/session")
    async def logout(request: Request, response: Response):
        if pocket:
            pocket.logout(request,response)
        return {"authenticated": development}

    @app.get("/api/v1/status")
    async def status():
        return {"name": settings.name, "version": VERSION, "server_time": time.time(), "timezone": settings.timezone,
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
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})

    # Register frontend files after API and authentication routes.
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, check_dir=False), name="frontend")
    return app


app = create_app()
