import asyncio
import time
from pathlib import Path
from app.config import Settings, LightConfig
from app.driver import DeviceUnavailable
from tests.support import FakeDriver
from app.service import LightController, LightService
from app.storage import Storage


def settings():
    return Settings(lights=[LightConfig(id="bedroom", name="房间吸顶灯", host="192.168.111.6")])


class RecordingDriver(FakeDriver):
    def __init__(self, config):
        super().__init__(config)
        self.writes = []
        self.concurrent = 0
        self.max_concurrent = 0

    def write(self, target):
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            self.writes.append(target.copy())
            return super().write(target)
        finally:
            self.concurrent -= 1


def test_startup_reads_without_writing(tmp_path):
    async def run():
        storage = Storage(tmp_path / "db")
        config = settings().lights[0]
        driver = RecordingDriver(config)
        controller = LightController(config, settings(), storage, driver)
        await controller.start()
        await asyncio.sleep(.1)
        assert controller.online
        assert driver.writes == []
        await controller.stop()
        storage.close()
    asyncio.run(run())


def test_one_lost_udp_read_is_retried_without_writes(tmp_path):
    class TransientDriver(RecordingDriver):
        attempts = 0
        def read(self):
            self.attempts += 1
            if self.attempts == 1:
                raise DeviceUnavailable("临时丢包")
            return super().read()
    async def run():
        storage = Storage(tmp_path / "db")
        config = settings().lights[0]
        driver = TransientDriver(config)
        controller = LightController(config, settings(), storage, driver)
        assert await controller.read()
        assert controller.online and driver.attempts == 2
        assert driver.writes == []
        assert not [event for event in storage.events() if event["message"] == "灯具连接中断"]
        await controller.stop()
        storage.close()
    asyncio.run(run())


def test_off_settings_staged_and_applied_on_explicit_on(tmp_path):
    async def run():
        storage = Storage(tmp_path / "db")
        config = settings().lights[0]
        driver = RecordingDriver(config)
        driver.state.power = False
        controller = LightController(config, settings(), storage, driver)
        staged = storage.new_operation(config.id, {"color_temperature_kelvin": 3200, "brightness_percent": 15}, "manual", 20)
        await controller.execute(staged)
        assert storage.get("operations", staged["id"])["status"] == "staged"
        assert driver.writes == []
        assert driver.state.power is False
        assert storage.get("preferences", config.id)["brightness_percent"] == 15
        on = storage.new_operation(config.id, {"power": True}, "manual", 20)
        await controller.execute(on)
        assert driver.state.power is True and driver.state.color_temperature_kelvin == 3200
        assert driver.state.brightness_percent == 15
        assert storage.get("preferences", config.id) == {}
        await controller.stop()
        storage.close()
    asyncio.run(run())


def test_expired_or_offline_commands_never_replay(tmp_path):
    async def run():
        storage = Storage(tmp_path / "db")
        config = settings().lights[0]
        driver = RecordingDriver(config)
        controller = LightController(config, settings(), storage, driver)
        op = storage.new_operation(config.id, {"power": False}, "manual", 20)
        op["expires_at"] = time.time()-1
        await controller.execute(op)
        assert storage.get("operations", op["id"])["status"] == "expired"
        driver.online = False
        op = storage.new_operation(config.id, {"power": False}, "manual", 20)
        await controller.execute(op)
        assert storage.get("operations", op["id"])["status"] == "failed"
        driver.online = True
        await controller.read()
        assert driver.writes == [] and driver.state.power
        await controller.stop()
        storage.close()
    asyncio.run(run())


def test_queue_serializes_writes_and_polling(tmp_path):
    async def run():
        storage = Storage(tmp_path / "db")
        config = settings().lights[0]
        driver = RecordingDriver(config)
        controller = LightController(config, settings(), storage, driver)
        await controller.start()
        operations = [controller.submit({"brightness_percent": value}) for value in (10, 20, 30, 40)]
        await asyncio.wait_for(controller.queue.join(), 4)
        assert driver.max_concurrent == 1
        assert driver.state.brightness_percent == 40
        assert all(storage.get("operations", op["id"])["status"] == "confirmed" for op in operations)
        await controller.stop()
        storage.close()
    asyncio.run(run())


def test_due_timer_and_cancellation(tmp_path):
    async def run():
        storage = Storage(tmp_path / "db")
        service = LightService(settings(), storage)
        timer = service.set_timer("bedroom", 1)
        service.tick_timers(timer["due_at"] + .1)
        current = storage.get("timers", "bedroom")
        assert current["status"] == "executing"
        controller = service.lights["bedroom"]
        op = storage.get("operations", current["operation_id"])
        service.cancel_timer("bedroom")
        await controller.execute(op)
        assert storage.get("operations", op["id"])["status"] == "cancelled"
        assert controller.driver.state.power
        timer = service.set_timer("bedroom", 1)
        service.tick_timers(timer["due_at"] + .1)
        current = storage.get("timers", "bedroom")
        await controller.execute(storage.get("operations", current["operation_id"]))
        assert controller.driver.state.power is False
        assert storage.get("timers", "bedroom")["status"] == "completed"
        await service.stop()
        storage.close()
    asyncio.run(run())


def test_restart_preserves_settings_scenes_and_timer_but_not_commands(tmp_path):
    path = tmp_path / "db"
    store = Storage(path)
    service = LightService(settings(), store)
    store.put("preferences", "bedroom", {"color_temperature_kelvin": 3200})
    scene = store.get("scenes", "bedroom-reading")
    scene["name"] = "自定义阅读"
    store.put("scenes", scene["id"], scene)
    store.delete("scenes", "bedroom-night")
    timer = service.set_timer("bedroom", 30)
    op = store.new_operation("bedroom", {"power": True}, "manual", 20)
    store.close()
    restored = Storage(path)
    restored_service = LightService(settings(), restored)
    assert restored.get("preferences", "bedroom")["color_temperature_kelvin"] == 3200
    assert restored.get("scenes", scene["id"])["name"] == "自定义阅读"
    assert restored.get("scenes", "bedroom-night") is None
    assert restored.get("operations", op["id"])["status"] == "failed"
    assert restored.get("timers", "bedroom")["due_at"] == timer["due_at"]
    restored_service.tick_timers(timer["due_at"] + 121)
    assert restored.get("timers", "bedroom")["status"] == "expired"
    restored.close()


def test_partial_write_failure_keeps_observed_state(tmp_path):
    class PartialDriver(FakeDriver):
        def write(self, target):
            self.state.power = True
            raise DeviceUnavailable("色温设置未确认")
    async def run():
        store = Storage(tmp_path / "db")
        config = settings().lights[0]
        driver = PartialDriver(config)
        driver.state.power = False
        controller = LightController(config, settings(), store, driver)
        op = store.new_operation("bedroom", {"power":True,"color_temperature_kelvin":3200}, "manual", 20)
        await controller.execute(op)
        assert store.get("operations", op["id"])["status"] == "failed"
        assert controller.view()["state"]["power"] is True
        assert controller.view()["state"]["color_temperature_kelvin"] == 4000
        await controller.stop()
        store.close()
    asyncio.run(run())
