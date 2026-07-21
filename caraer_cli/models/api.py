from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CaraerValidationError(BaseModel):
    field: str | None = None
    message: str | None = None
    correctionSuggestion: str | None = None


class ErrorEnvelope(BaseModel):
    message: str = "Request failed."
    status: int = 500
    errors: list[CaraerValidationError] | None = None
    roles: list[str] | None = None
    scopes: list[str] | None = None
    stackTrace: str | None = None


class SuccessEnvelope(BaseModel):
    message: str = "Success"
    data: Any = None


class PaginationEnvelope(SuccessEnvelope):
    total: int = 0
    page: int = 1
    perPage: int = 25
    lastPage: int = 1


class AuthTokenModel(BaseModel):
    token: str | None = None
    expiresAt: int | None = None


class CompanyModel(BaseModel):
    uuid: str
    name: str | None = None


class UserModel(BaseModel):
    uuid: str
    email: str | None = None
    globalRole: str | None = None
    token: AuthTokenModel | None = None
    companies: list[CompanyModel] = Field(default_factory=list)
