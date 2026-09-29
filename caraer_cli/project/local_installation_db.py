"""Local Postgres shim for POST /api/v2/apps/{uuid}/installation/db."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from caraer_cli.project.schema import ProjectConfig

_FORBIDDEN = re.compile(
    r"(?i)\b(set|reset|copy|dblink|create\s+schema|drop\s+schema|alter\s+schema|"
    r"create\s+extension|alter\s+system|comment\s+on\s+schema)\b"
    r"|search_path|pg_read_file|lo_import|lo_export"
)
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def run_local_installation_sql(
    root: Path, config: ProjectConfig, body: dict[str, Any]
) -> dict[str, Any]:
    statements = body.get("statements")
    if not isinstance(statements, list) or not statements:
        raise ValueError("Body must include statements: [{ sql, params }]")
    dsn = os.environ.get("CARAER_INSTALLATION_DB_URL") or "postgresql://127.0.0.1:5432/caraer_installations"
    schema = _schema_name(config)
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Local installation SQL needs psycopg. Install it or point "
            "CARAER_INSTALLATION_DB_URL at a reachable Postgres."
        ) from exc
    results: list[dict[str, Any]] = []
    with psycopg.connect(_as_psycopg_dsn(dsn), autocommit=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(f'SET LOCAL search_path TO "{schema}"')
            for item in statements:
                if not isinstance(item, dict):
                    continue
                sql = str(item.get("sql") or "").strip()
                _validate_sql(sql)
                params = item.get("params") if isinstance(item.get("params"), list) else []
                cursor.execute(sql, params)
                if cursor.description:
                    columns = [col.name for col in cursor.description]
                    rows = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
                    results.append({"rows": rows})
                else:
                    results.append({"rowCount": cursor.rowcount})
        connection.commit()
    return {"schema": schema, "results": results}


def _schema_name(config: ProjectConfig) -> str:
    app = str(config.appUuid or "00000000-0000-0000-0000-000000000001")
    company = os.environ.get("CARAER_COMPANY_UUID") or "00000000-0000-0000-0000-000000000002"
    if not _UUID.fullmatch(app) or not _UUID.fullmatch(company):
        raise ValueError("Installation schema needs app and company UUIDs")
    return f"{app}_{company}"


def _validate_sql(sql: str) -> None:
    if not sql:
        raise ValueError("Each statement needs sql")
    if ";" in sql:
        raise ValueError("One SQL statement per item; do not include ';'")
    if _FORBIDDEN.search(sql):
        raise ValueError("Statement cannot change search_path, schemas, extensions, or use COPY/dblink")


def _as_psycopg_dsn(url: str) -> str:
    if url.startswith("jdbc:postgresql://"):
        parsed = urlparse(url[len("jdbc:") :])
        user = os.environ.get("CARAER_INSTALLATION_DB_USER") or "caraer_install"
        password = os.environ.get("CARAER_INSTALLATION_DB_PASSWORD") or ""
        netloc = parsed.netloc
        if "@" not in netloc:
            auth = f"{user}:{password}@" if password else f"{user}@"
            netloc = auth + netloc
        return urlunparse(("postgresql", netloc, parsed.path, "", parsed.query, ""))
    return url
