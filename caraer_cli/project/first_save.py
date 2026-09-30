"""Shape the first app save so name-only functions are not created yet."""

from __future__ import annotations

from typing import Any

_LIFECYCLE_HOOK_KEYS = (
    "installWebhook",
    "uninstallWebhook",
    "rotateWebhook",
    "updateWebhook",
)


def _function_ref_has_no_uuid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    function = value.get("serverlessFunction")
    if not isinstance(function, dict):
        return False
    return not str(function.get("uuid") or "").strip()


def defer_unlinked_functions(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop name-only function hooks from the first save.

    Lifecycle and app-bar webhooks name a function that does not exist until
    the build is deployed. Saving that stub now creates a ServerlessFunction
    with no runtime, which the API rejects.
    """
    out = dict(payload)
    for key in _LIFECYCLE_HOOK_KEYS:
        if _function_ref_has_no_uuid(out.get(key)):
            out.pop(key, None)
    bars = out.get("appBars")
    if isinstance(bars, list):
        out["appBars"] = [
            bar
            for bar in bars
            if not (
                isinstance(bar, dict)
                and _function_ref_has_no_uuid(bar.get("webhook"))
            )
        ]
    return out
