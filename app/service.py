import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from .driver import DemoDriver, OppleDriver, DeviceUnavailable
from .storage import utc_now

log = logging.getLogger(__name__)


class LightController:
    def __init__(self, config, settings, storage, driver=None):
        self.config, self.settings, self.storage = config, settings, storage
        self.driver = driver or (DemoDriver(config) if settings.mode == "demo" else OppleDriver(config.host))
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"opple-{config.id}")
        self.queue = asyncio.Queue(maxsize=32)
        self.online = False
        self.reading = None
        self.last_seen = None
        self.error = None
        self.tasks = []
        self.busy = False

    async def start(self):
        self.tasks = [asyncio.create_task(self.worker()), asyncio.create_task(self.poller())]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        # Executor owns socket lifetime. A cancellation never releases the socket
        # to a second concurrent call; close runs after existing work finishes.
        await asyncio.get_running_loop().run_in_executor(self.executor, self.driver.close)
        self.executor.shutdown(wait=True)

    async def call(self, method, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, method, *args)

    def observe(self, reading):
        was_offline = not self.online
        self.reading, self.online, self.error, self.last_seen = reading, True, None, utc_now()
        if was_offline:
            self.storage.event(self.config.id, "connection", "灯具已连接" if self.settings.mode == "real" else "演示灯具已就绪")

    async def read(self):
        # UDP may lose a single reply. Retry the read once before declaring the
        # device offline; never replay a write or keep commands for later.
        for attempt in range(2):
            try:
                self.observe(await self.call(self.driver.read))
                return True
            except DeviceUnavailable as exc:
                if attempt == 0:
                    await asyncio.sleep(.2)
                    continue
                if self.online:
                    self.storage.event(self.config.id, "connection", "灯具连接中断")
                self.online, self.error = False, str(exc)
                return False

    def view(self):
        pending = self.storage.get("preferences", self.config.id) or {}
        return dict(id=self.config.id, name=self.config.name, host=str(self.config.host), online=self.online,
                    state=vars(self.reading) if self.reading else None, pending_settings=pending,
                    last_seen=self.last_seen, error=self.error, busy=self.busy or not self.queue.empty(),
                    capabilities=dict(min_kelvin=self.config.min_kelvin, max_kelvin=self.config.max_kelvin),
                    timer=self.storage.get("timers", self.config.id))

    def validate_target(self, target):
        if not target:
            raise ValueError("至少提供一个控制参数")
        kelvin = target.get("color_temperature_kelvin")
        if kelvin is not None and not self.config.min_kelvin <= kelvin <= self.config.max_kelvin:
            raise ValueError(f"色温需要在 {self.config.min_kelvin}–{self.config.max_kelvin} K 之间")

    def submit(self, target, source="manual", timer_id=None):
        self.validate_target(target)
        if self.queue.full():
            raise OverflowError("操作过于频繁，请稍后重试")
        op = self.storage.new_operation(self.config.id, target, source, self.settings.command_ttl_seconds)
        if timer_id:
            op["timer_id"] = timer_id
            self.storage.put("operations", op["id"], op)
        self.queue.put_nowait(op["id"])
        return op

    def finish(self, op, status, message):
        op.update(status=status, message=message, finished_at=utc_now())
        self.storage.put("operations", op["id"], op)
        self.storage.event(self.config.id, "control" if status in ("confirmed", "staged") else "error", message)
        if op.get("timer_id"):
            timer = self.storage.get("timers", self.config.id)
            if timer and timer["id"] == op["timer_id"] and timer["status"] == "executing":
                timer.update(status="completed" if status == "confirmed" else "failed", message=message)
                self.storage.put("timers", self.config.id, timer)

    async def execute(self, op):
        if time.time() > op["expires_at"]:
            self.finish(op, "expired", "操作已过期，请重新操作")
            return
        if op.get("timer_id"):
            timer = self.storage.get("timers", self.config.id)
            if not timer or timer["id"] != op["timer_id"] or timer["status"] != "executing":
                self.finish(op, "cancelled", "倒计时已取消")
                return
        op.update(status="running", message="正在执行")
        self.storage.put("operations", op["id"], op)
        target = op["target"].copy()
        # Read before writes. Do not trust a previous cached "already on" state.
        if not await self.read():
            self.finish(op, "failed", self.error)
            return
        pending = self.storage.get("preferences", self.config.id) or {}
        parameters = {key: value for key, value in target.items() if key != "power"}
        will_be_off = target.get("power") is False or (not self.reading.power and target.get("power") is not True)
        if will_be_off:
            if target.get("power") is False:
                try:
                    self.observe(await self.call(self.driver.write, {"power": False}))
                except DeviceUnavailable as exc:
                    await self.read()
                    self.finish(op, "failed", str(exc))
                    return
            if parameters:
                pending.update(parameters)
                self.storage.put("preferences", self.config.id, pending)
            self.finish(op, "staged" if parameters else "confirmed", "已保存下次开灯设置" if parameters else "已关灯")
            return
        # Apply staged settings only on an explicit turn-on; sliders while already
        # on control actual state without resetting unrelated settings.
        if target.get("power") is True:
            target = {**pending, **target}
        try:
            self.observe(await self.call(self.driver.write, target))
            if op["target"].get("power") is True:
                self.storage.put("preferences", self.config.id, {})
            message = "倒计时结束，已关灯" if op["source"] == "timer" else "灯光已更新"
            self.finish(op, "confirmed", message)
        except DeviceUnavailable as exc:
            await self.read()  # Preserve observed partial results, never optimistic state.
            self.finish(op, "failed", str(exc))

    async def worker(self):
        while True:
            item = await self.queue.get()
            self.busy = True
            try:
                if item == "__poll__":
                    await self.read()
                else:
                    op = self.storage.get("operations", item)
                    await self.execute(op)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Device worker failure")
                if item != "__poll__":
                    self.finish(op, "failed", "操作未完成，请刷新状态后重试")
            finally:
                self.busy = False
                self.queue.task_done()

    async def poller(self):
        while True:
            if not self.busy and self.queue.empty():
                self.queue.put_nowait("__poll__")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    def refresh(self):
        if not self.busy and self.queue.empty():
            self.queue.put_nowait("__poll__")


class LightService:
    def __init__(self, settings, storage):
        self.settings, self.storage = settings, storage
        self.lights = {config.id: LightController(config, settings, storage) for config in settings.lights}
        self.timer_task = None
        for light in self.lights.values():
            config = light.config
            if storage.get("metadata", f"seeded-{config.id}"):
                continue
            for key, name, kelvin, brightness, icon in [
                ("daily", "日常", 4000, 70, "sun"),
                ("reading", "阅读", 5000, 90, "book"),
                ("night", "夜间", 3000, 10, "moon"),
            ]:
                scene_id = f"{config.id}-{key}"
                if not storage.get("scenes", scene_id):
                    storage.put("scenes", scene_id, dict(id=scene_id, light_id=config.id, name=name, icon=icon,
                        color_temperature_kelvin=max(config.min_kelvin, min(config.max_kelvin, kelvin)), brightness_percent=brightness))

            storage.put("metadata", f"seeded-{config.id}", True)

    async def start(self):
        for light in self.lights.values():
            await light.start()
        self.timer_task = asyncio.create_task(self.timer_loop())

    async def stop(self):
        if self.timer_task:
            self.timer_task.cancel()
            await asyncio.gather(self.timer_task, return_exceptions=True)
        for light in self.lights.values():
            await light.stop()

    def set_timer(self, light_id, minutes):
        timer = dict(id=uuid4().hex, light_id=light_id, created_at=utc_now(), due_at=time.time()+minutes*60, minutes=minutes, status="active")
        self.storage.put("timers", light_id, timer)
        self.storage.event(light_id, "timer", f"已设置 {minutes} 分钟后关灯")
        return timer

    def cancel_timer(self, light_id):
        timer = self.storage.get("timers", light_id)
        if timer and timer["status"] in ("active", "executing"):
            timer.update(status="cancelled")
            self.storage.put("timers", light_id, timer)
            self.storage.event(light_id, "timer", "已取消倒计时")

    def tick_timers(self, now=None):
        now = time.time() if now is None else now
        for timer in self.storage.all("timers"):
            if timer["status"] not in ("active", "executing"):
                continue
            if timer["light_id"] not in self.lights:
                continue
            if timer["status"] == "executing":
                op = self.storage.get("operations", timer.get("operation_id", ""))
                if op and op["status"] in ("pending", "running"):
                    continue
                timer.update(status="failed", message="服务重启或操作中断，关灯任务未重放")
                self.storage.put("timers", timer["light_id"], timer)
                continue
            if now < timer["due_at"]:
                continue
            if now - timer["due_at"] > 120:
                timer.update(status="expired", message="倒计时已过期，未补执行")
                self.storage.put("timers", timer["light_id"], timer)
                self.storage.event(timer["light_id"], "timer", "倒计时已过期，未补执行")
                continue
            try:
                op = self.lights[timer["light_id"]].submit({"power": False}, "timer", timer["id"])
                timer.update(status="executing", operation_id=op["id"])
                self.storage.put("timers", timer["light_id"], timer)
            except OverflowError:
                # The 120 second expiration still applies on the next tick.
                continue

    async def timer_loop(self):
        while True:
            self.tick_timers()
            await asyncio.sleep(1)
