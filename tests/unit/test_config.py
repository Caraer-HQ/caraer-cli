from caraer_cli.state.config import CliConfig, active_profile


def test_default_has_dev_profile() -> None:
    cfg = CliConfig.default()
    key, profile = active_profile(cfg)
    assert key == "dev"
    assert profile.base_url
