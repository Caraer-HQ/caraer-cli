"""Interactive CLI wizards."""

__all__ = ["run_public_app_wizard"]


def run_public_app_wizard(*args, **kwargs):
    from caraer_cli.wizard.public_app import run_public_app_wizard as _run

    return _run(*args, **kwargs)
