from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


CONFIG_DIRNAME = "caraer-cli"
CONFIG_FILENAME = "config.toml"
DEFAULT_PROFILE = "prod"

# Built-in profiles. `prod` is the default so a new install talks to production.
PROFILE_BASE_URLS: dict[str, str] = {
    "local": "http://localhost:8080",
    "dev": "https://v2.dev.api.caraer.com",
    "staging": "https://v2.staging.api.caraer.com",
    "prod": "https://api.caraer.com",
}

# Earlier releases shipped these hosts. Rewrite them; leave custom URLs alone.
_LEGACY_PROFILE_URLS: dict[str, frozenset[str]] = {
    "dev": frozenset(
        {
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "https://dev.api.caraer.com",
        }
    ),
    "staging": frozenset(
        {
            "https://staging.caraer.com",
            "https://staging.api.caraer.com",
        }
    ),
    "prod": frozenset({"https://caraer.com"}),
}


@dataclass
class ProfileConfig:
    base_url: str
    company_uuid: str | None = None
    sandbox_uuid: str | None = None
    app_uuid: str | None = None
    app_file: str | None = None
    output: str = "table"
    timeout_seconds: float = 120.0
    verify_ssl: bool = True


@dataclass
class CliConfig:
    active_profile: str = DEFAULT_PROFILE
    profiles: dict[str, ProfileConfig] = field(default_factory=dict)

    @staticmethod
    def default() -> "CliConfig":
        return CliConfig(
            active_profile=DEFAULT_PROFILE,
            profiles={
                name: ProfileConfig(base_url=url)
                for name, url in PROFILE_BASE_URLS.items()
            },
        )


def config_dir() -> Path:
    return Path(user_config_dir(CONFIG_DIRNAME))


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return '""'
    return str(value)


def _to_toml(cfg: CliConfig) -> str:
    lines: list[str] = [f'active_profile = "{cfg.active_profile}"', ""]
    for profile_name, profile in cfg.profiles.items():
        lines.extend(
            [
                f"[profiles.{profile_name}]",
                f"base_url = {_toml_value(profile.base_url)}",
                f"company_uuid = {_toml_value(profile.company_uuid)}",
                f"sandbox_uuid = {_toml_value(profile.sandbox_uuid)}",
                f"app_uuid = {_toml_value(profile.app_uuid)}",
                f"app_file = {_toml_value(profile.app_file)}",
                f"output = {_toml_value(profile.output)}",
                f"timeout_seconds = {_toml_value(profile.timeout_seconds)}",
                f"verify_ssl = {_toml_value(profile.verify_ssl)}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def load_config() -> CliConfig:
    path = config_path()
    if not path.exists():
        cfg = CliConfig.default()
        save_config(cfg)
        return cfg

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    cfg = CliConfig.default()
    cfg.active_profile = raw.get("active_profile", cfg.active_profile)
    profile_block = raw.get("profiles", {})
    if isinstance(profile_block, dict):
        cfg.profiles = {}
        for name, value in profile_block.items():
            if not isinstance(value, dict):
                continue
            fallback = PROFILE_BASE_URLS.get(name, PROFILE_BASE_URLS[DEFAULT_PROFILE])
            cfg.profiles[name] = ProfileConfig(
                base_url=str(value.get("base_url") or fallback),
                company_uuid=value.get("company_uuid") or None,
                sandbox_uuid=value.get("sandbox_uuid") or None,
                app_uuid=value.get("app_uuid") or None,
                app_file=value.get("app_file") or None,
                output=str(value.get("output", "table")),
                timeout_seconds=float(value.get("timeout_seconds", 120.0)),
                verify_ssl=bool(value.get("verify_ssl", True)),
            )

    if apply_builtin_profiles(cfg):
        save_config(cfg)
    return cfg


def _url_key(url: str) -> str:
    return url.strip().rstrip("/")


def _profile_has_selection(profile: ProfileConfig) -> bool:
    return any(
        (
            profile.company_uuid,
            profile.sandbox_uuid,
            profile.app_uuid,
            profile.app_file,
        )
    )


def apply_builtin_profiles(cfg: CliConfig) -> bool:
    """Ensure the built-in profiles exist and use the current API hosts.

    Custom base URLs are kept. A config from the old default (`dev` pointed at
    localhost and was selected) moves that localhost session onto `local` and
    selects `prod` when nothing was configured yet.
    """
    changed = False
    dev = cfg.profiles.get("dev")
    if dev is not None and _url_key(dev.base_url) in _LEGACY_PROFILE_URLS["dev"]:
        local = cfg.profiles.get("local")
        local_had_selection = local is not None and _profile_has_selection(local)
        dev_had_selection = _profile_has_selection(dev)
        if local is None or (dev_had_selection and not local_had_selection):
            cfg.profiles["local"] = replace(dev, base_url=PROFILE_BASE_URLS["local"])
        dev.base_url = PROFILE_BASE_URLS["dev"]
        if dev_had_selection and not local_had_selection:
            dev.company_uuid = None
            dev.sandbox_uuid = None
            dev.app_uuid = None
            dev.app_file = None
        if cfg.active_profile == "dev":
            local_now = cfg.profiles["local"]
            cfg.active_profile = (
                "local" if _profile_has_selection(local_now) else DEFAULT_PROFILE
            )
        changed = True

    for name, url in PROFILE_BASE_URLS.items():
        profile = cfg.profiles.get(name)
        if profile is None:
            cfg.profiles[name] = ProfileConfig(base_url=url)
            changed = True
            continue
        legacy = _LEGACY_PROFILE_URLS.get(name, frozenset())
        if _url_key(profile.base_url) in legacy:
            profile.base_url = url
            changed = True

    if cfg.active_profile not in cfg.profiles:
        cfg.active_profile = (
            DEFAULT_PROFILE
            if DEFAULT_PROFILE in cfg.profiles
            else next(iter(cfg.profiles), DEFAULT_PROFILE)
        )
        changed = True
    return changed


def save_config(cfg: CliConfig) -> None:
    dir_path = config_dir()
    dir_path.mkdir(parents=True, exist_ok=True)
    path = config_path()
    path.write_text(_to_toml(cfg), encoding="utf-8")
    os.chmod(path, 0o600)


def active_profile(cfg: CliConfig, override: str | None = None) -> tuple[str, ProfileConfig]:
    key = override or cfg.active_profile
    if key not in cfg.profiles:
        raise ValueError(f"Unknown profile '{key}'.")
    return key, cfg.profiles[key]


def profile_as_dict(profile: ProfileConfig) -> dict[str, Any]:
    return {
        "base_url": profile.base_url,
        "company_uuid": profile.company_uuid,
        "sandbox_uuid": profile.sandbox_uuid,
        "app_uuid": profile.app_uuid,
        "app_file": profile.app_file,
        "output": profile.output,
        "timeout_seconds": profile.timeout_seconds,
        "verify_ssl": profile.verify_ssl,
    }
