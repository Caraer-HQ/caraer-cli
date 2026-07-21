from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import keyring
from platformdirs import user_config_dir


APP_NAME = "caraer-cli"
SERVICE_NAME = "caraer-cli-session"


def _fallback_session_path() -> Path:
    path = Path(user_config_dir(APP_NAME)) / "sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o600)
    return path


def _load_fallback() -> dict[str, Any]:
    path = _fallback_session_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_fallback(data: dict[str, Any]) -> None:
    path = _fallback_session_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


def get_session_token(profile: str) -> str | None:
    try:
        token = keyring.get_password(SERVICE_NAME, profile)
        if token:
            return token
    except Exception:
        pass

    data = _load_fallback()
    value = data.get(profile, {})
    token = value.get("token")
    return str(token) if token else None


def set_session_token(profile: str, token: str) -> None:
    wrote_keyring = False
    try:
        keyring.set_password(SERVICE_NAME, profile, token)
        wrote_keyring = True
    except Exception:
        wrote_keyring = False

    if not wrote_keyring:
        data = _load_fallback()
        data.setdefault(profile, {})
        data[profile]["token"] = token
        _save_fallback(data)


def clear_session_token(profile: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, profile)
    except Exception:
        pass

    data = _load_fallback()
    if profile in data and isinstance(data[profile], dict):
        data[profile].pop("token", None)
    _save_fallback(data)
