from pathlib import Path

import pytest

from caraer_cli.state.config import (
    DEFAULT_PROFILE,
    PROFILE_BASE_URLS,
    CliConfig,
    ProfileConfig,
    active_profile,
    load_config,
    save_config,
)


def test_default_profile_is_prod() -> None:
    cfg = CliConfig.default()
    key, profile = active_profile(cfg)
    assert key == DEFAULT_PROFILE
    assert profile.base_url == "https://api.caraer.com"
    assert cfg.profiles["local"].base_url == "http://localhost:8080"
    assert cfg.profiles["dev"].base_url == "https://v2.dev.api.caraer.com"
    assert cfg.profiles["staging"].base_url == "https://v2.staging.api.caraer.com"


def test_load_rewrites_legacy_default_onto_prod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("caraer_cli.state.config.config_dir", lambda: tmp_path)
    save_config(
        CliConfig(
            active_profile="dev",
            profiles={
                "dev": ProfileConfig(base_url="http://localhost:8080"),
                "staging": ProfileConfig(base_url="https://staging.api.caraer.com"),
                "prod": ProfileConfig(base_url="https://caraer.com"),
            },
        )
    )

    cfg = load_config()

    assert cfg.active_profile == "prod"
    assert cfg.profiles["prod"].base_url == PROFILE_BASE_URLS["prod"]
    assert cfg.profiles["dev"].base_url == PROFILE_BASE_URLS["dev"]
    assert cfg.profiles["staging"].base_url == PROFILE_BASE_URLS["staging"]
    assert cfg.profiles["local"].base_url == PROFILE_BASE_URLS["local"]


def test_load_keeps_localhost_session_on_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("caraer_cli.state.config.config_dir", lambda: tmp_path)
    save_config(
        CliConfig(
            active_profile="dev",
            profiles={
                "dev": ProfileConfig(
                    base_url="http://localhost:8080",
                    company_uuid="company-1",
                ),
            },
        )
    )

    cfg = load_config()

    assert cfg.active_profile == "local"
    assert cfg.profiles["local"].company_uuid == "company-1"
    assert cfg.profiles["local"].base_url == "http://localhost:8080"
    assert cfg.profiles["dev"].base_url == "https://v2.dev.api.caraer.com"
    assert cfg.profiles["dev"].company_uuid is None


def test_load_keeps_custom_profile_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("caraer_cli.state.config.config_dir", lambda: tmp_path)
    save_config(
        CliConfig(
            active_profile="staging",
            profiles={
                "staging": ProfileConfig(base_url="https://staging.example.com"),
            },
        )
    )

    cfg = load_config()

    assert cfg.active_profile == "staging"
    assert cfg.profiles["staging"].base_url == "https://staging.example.com"
    assert cfg.profiles["prod"].base_url == "https://api.caraer.com"
