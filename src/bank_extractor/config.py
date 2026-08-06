from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from bank_extractor.errors import ConfigError
from bank_extractor.models import Period

ExportFormat = Literal["json", "csv", "parquet"]


def _default_formats() -> list[ExportFormat]:
    return ["json", "csv"]


class SessionConfig(BaseModel):
    mode: Literal["attach", "launch", "auto"] = "launch"
    cdp_url: str = "http://localhost:9222"
    user_data_dir: Path = Path("./.profiles/default")
    headless: bool = False
    auth_timeout_s: int = 300


class OutputConfig(BaseModel):
    dir: Path = Path("./out")
    formats: list[ExportFormat] = Field(default_factory=_default_formats)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: Path | None = None


class RetryConfig(BaseModel):
    attempts: int = Field(default=3, ge=1, le=10)
    backoff_s: float = Field(default=1.0, ge=0)


class TimeoutConfig(BaseModel):
    navigation_s: int = Field(default=20, ge=1)
    selector_s: int = Field(default=10, ge=1)


class AppConfig(BaseModel):
    bank: str
    base_url: str
    period: Period
    consent_file: Path
    session: SessionConfig = Field(default_factory=SessionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    retries: RetryConfig = Field(default_factory=RetryConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)


def load_config(path: Path) -> AppConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"файл конфигурации не найден: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"не удалось разобрать YAML: {path}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"ожидался объект верхнего уровня: {path}")

    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"конфигурация невалидна: {exc}") from exc
