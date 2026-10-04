import os
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, model_validator


class LightConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    host: IPvAnyAddress
    min_kelvin: int = Field(default=3000, ge=2700, le=6500)
    max_kelvin: int = Field(default=5700, ge=2700, le=6500)
    default_kelvin: int = 4000
    default_brightness: int = Field(default=70, ge=1, le=100)

    @model_validator(mode="after")
    def validate_range(self):
        if self.host.version != 4:
            raise ValueError("OPPLE 协议需要 IPv4 地址")
        if not self.min_kelvin <= self.default_kelvin <= self.max_kelvin:
            raise ValueError("默认色温必须位于设备色温范围内")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "一室光"
    mode: Literal["real", "demo"] = "real"
    poll_interval_seconds: int = Field(default=10, ge=3, le=300)
    command_ttl_seconds: int = Field(default=20, ge=5, le=60)
    timezone: str = "Asia/Shanghai"
    lights: list[LightConfig] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({light.id for light in self.lights}) != len(self.lights):
            raise ValueError("灯具 ID 必须唯一")
        from zoneinfo import ZoneInfo
        ZoneInfo(self.timezone)
        return self


def load_settings() -> Settings:
    path = Path(os.getenv("OPPLE_CONFIG", "config/config.yaml"))
    with path.open(encoding="utf-8") as file:
        values = yaml.safe_load(file)
    if os.getenv("OPPLE_MODE"):
        values["mode"] = os.environ["OPPLE_MODE"]
    return Settings.model_validate(values)
