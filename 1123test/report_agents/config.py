"""실행 설정. 값은 모두 1123test/.env에서 읽는다 (.env.example 참고)."""

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _get(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f".env에 {name} 값이 없습니다. .env.example을 참고해 채워주세요.")
    return value


def _flag(name: str) -> bool:
    return _get(name).lower() in ("1", "true", "yes", "on")


def _path(name: str) -> Path:
    p = Path(_get(name))
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    use_search: bool
    max_rework: int
    max_concurrency: int
    temperature: float
    reference_pdf: Path
    brief_path: Path
    config_dir: Path
    workspace_dir: Path
    dry_run_fixture: Path
    web_host: str
    web_port: int

    @property
    def api_key_ready(self) -> bool:
        return bool(self.api_key) and self.api_key.isascii()


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env", override=True)
    host = _get("WEB_HOST")
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        raise ConfigError(f"WEB_HOST={host}: 이 서비스는 로컬 전용이라 127.0.0.1 또는 localhost만 쓸 수 있습니다.")
    return Settings(
        api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
        model=_get("MODEL_NAME"),
        use_search=_flag("USE_SEARCH"),
        max_rework=int(_get("MAX_REWORK")),
        max_concurrency=int(_get("MAX_CONCURRENCY")),
        temperature=float(_get("TEMPERATURE")),
        reference_pdf=_path("REFERENCE_PDF"),
        brief_path=_path("BRIEF_PATH"),
        config_dir=_path("CONFIG_DIR"),
        workspace_dir=_path("WORKSPACE_DIR"),
        dry_run_fixture=_path("DRY_RUN_FIXTURE"),
        web_host=host,
        web_port=int(_get("WEB_PORT")),
    )
