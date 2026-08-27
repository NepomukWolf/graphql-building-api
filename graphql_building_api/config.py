import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = API_DIR.parent
CONFIG_FILE = PROJECT_ROOT / "config.toml"
STATIC_DIR = API_DIR / "static"
MODELS_DIR = STATIC_DIR / "models"


@dataclass(frozen=True)
class GeometryConfig:
    default_source: str = "FILE"
    respect_client_source: bool = True
    allow_dynamic_generation: bool = True
    cache_generated: bool = False


@dataclass(frozen=True)
class AppConfig:
    default_model: str = "2026-SampleModel"
    default_port: int = 8000
    geometry: GeometryConfig = GeometryConfig()
    disabled_extensions: tuple[str, ...] = ()


def _load_toml_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {}

    with CONFIG_FILE.open("rb") as config_file:
        return tomllib.load(config_file)


def _normalize_source(value: str | None) -> str:
    source = (value or "file").strip().upper()
    if source not in {"FILE", "MODEL"}:
        raise ValueError(f"Unsupported geometry source: {value}")
    return source


def load_config() -> AppConfig:
    raw_config = _load_toml_config()
    raw_geometry = raw_config.get("geometry", {})
    raw_extensions = raw_config.get("extensions", {})

    geometry = GeometryConfig(
        default_source=_normalize_source(raw_geometry.get("default_source", "file")),
        respect_client_source=raw_geometry.get("respect_client_source", True),
        allow_dynamic_generation=raw_geometry.get("allow_dynamic_generation", True),
        cache_generated=raw_geometry.get("cache_generated", False),
    )

    return AppConfig(
        default_model=raw_config.get("default_model", "2026-SampleModel"),
        default_port=raw_config.get("default_port", 8000),
        geometry=geometry,
        disabled_extensions=tuple(raw_extensions.get("disabled", [])),
    )


CONFIG = load_config()

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", CONFIG.default_model)
DEFAULT_PORT = int(os.environ.get("PORT", CONFIG.default_port))
GEOMETRY_CONFIG = CONFIG.geometry
DISABLED_EXTENSIONS = CONFIG.disabled_extensions
