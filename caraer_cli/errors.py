from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models.api import ErrorEnvelope


@dataclass
class CliError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass
class ApiError(CliError):
    status: int = 500
    payload: dict[str, Any] | None = None


class AuthError(ApiError):
    pass


class ValidationError(ApiError):
    pass


class ScopeError(ApiError):
    pass


class RoleError(ApiError):
    pass


class NotFoundError(ApiError):
    pass


class BackendError(ApiError):
    pass


def parse_api_error(status: int, payload: dict[str, Any] | None) -> ApiError:
    envelope = ErrorEnvelope.model_validate(payload or {})
    message = envelope.message or "Request failed."
    detail_lines: list[str] = []

    if envelope.errors:
        for item in envelope.errors:
            fragment = item.message or "Validation error"
            if item.field:
                fragment = f"{item.field}: {fragment}"
            if item.correctionSuggestion:
                fragment = f"{fragment} ({item.correctionSuggestion})"
            detail_lines.append(fragment)

    if envelope.scopes:
        detail_lines.append("Missing scopes: " + ", ".join(envelope.scopes))
    if envelope.roles:
        detail_lines.append("Missing roles: " + ", ".join(envelope.roles))

    request_id = envelope.requestId or envelope.correlationId
    if request_id:
        detail_lines.append(f"Request ID: {request_id}")

    if detail_lines:
        message = f"{message}\n" + "\n".join(detail_lines)

    kwargs = {"message": message, "status": status, "payload": payload}
    if status in (401, 423):
        return AuthError(**kwargs)
    if status == 403 and envelope.scopes:
        return ScopeError(**kwargs)
    if status == 403 and envelope.roles:
        return RoleError(**kwargs)
    if status == 404:
        return NotFoundError(**kwargs)
    if status == 400:
        return ValidationError(**kwargs)
    return BackendError(**kwargs)
