from __future__ import annotations

from caraer_cli.commands import billing


def test_billing_command_group_exists() -> None:
    assert billing.app is not None
    assert billing.subscription_app is not None
    assert billing.meter_app is not None
