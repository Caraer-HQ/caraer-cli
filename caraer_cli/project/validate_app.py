"""Local validation for Caraer app workspaces (manifest, functions, webhooks)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from caraer_cli.local_app import load_local_app
from caraer_cli.project.paths import app_manifest_path, functions_dir, webhooks_dir
from caraer_cli.project.schema import ProjectConfig, load_workspace
from caraer_cli.project.sync import discover_local_functions, list_local_function_names
from caraer_cli.project.webhooks_sync import discover_local_webhooks

Severity = Literal["error", "warning"]

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Mirrors AppCategoryCatalog main keys + legacy aliases accepted by the backend.
MAIN_CATEGORIES: dict[str, frozenset[str]] = {
    "productivity": frozenset(
        {"agenda", "tasks", "notes", "documents", "files", "automation", "forms"}
    ),
    "communication": frozenset(
        {
            "email",
            "chat",
            "meetings",
            "calling",
            "notifications",
            "customer_conversations",
            "social_messaging",
        }
    ),
    "recruitment": frozenset(
        {
            "ats",
            "job_posting",
            "sourcing",
            "candidate_communication",
            "career_sites",
            "screening",
            "interview_scheduling",
            "analytics",
        }
    ),
    "hr": frozenset(
        {
            "hris",
            "onboarding",
            "payroll",
            "contracts",
            "learning",
            "engagement",
            "compliance",
        }
    ),
    "marketing": frozenset(
        {
            "email_marketing",
            "social_media",
            "campaigns",
            "content",
            "seo",
            "advertising",
            "automation",
            "branding",
        }
    ),
    "sales": frozenset(
        {
            "crm",
            "lead_generation",
            "enrichment",
            "outreach",
            "proposals",
            "account_management",
            "analytics",
        }
    ),
    "data": frozenset(
        {
            "dashboards",
            "reporting",
            "spreadsheets",
            "visualization",
            "data_management",
            "predictions",
        }
    ),
    "finance": frozenset(
        {
            "invoicing",
            "payments",
            "bookkeeping",
            "expenses",
            "budgeting",
            "reporting",
        }
    ),
    "customer_support": frozenset(
        {
            "helpdesk",
            "ticketing",
            "live_chat",
            "knowledge_base",
            "feedback",
            "analytics",
        }
    ),
    "developer_tools": frozenset(
        {
            "code",
            "repositories",
            "apis",
            "webhooks",
            "devops",
            "monitoring",
            "testing",
            "no_code",
        }
    ),
    "education_and_learning": frozenset(
        {
            "courses",
            "training",
            "onboarding",
            "coaching",
            "assessments",
            "knowledge_sharing",
        }
    ),
}

LEGACY_MAIN_ALIASES = {
    "hr_recruiting": "recruitment",
    "recruiting": "recruitment",
    "blog": "marketing",
    "integrations": "developer_tools",
    "analytics": "data",
    "automation": "productivity",
}

LEGACY_ONLY_MAIN = frozenset(
    {"hr_recruiting", "integrations", "analytics", "automation", "blog"}
)


@dataclass
class ValidationIssue:
    severity: Severity
    path: str
    message: str


@dataclass
class ValidationReport:
    ok: bool
    root: str
    issues: list[ValidationIssue] = field(default_factory=list)
    functions: int = 0
    webhooks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "root": self.root,
            "functions": self.functions,
            "webhooks": self.webhooks,
            "errors": sum(1 for i in self.issues if i.severity == "error"),
            "warnings": sum(1 for i in self.issues if i.severity == "warning"),
            "issues": [asdict(i) for i in self.issues],
        }


def _issue(
    issues: list[ValidationIssue],
    severity: Severity,
    path: str,
    message: str,
) -> None:
    issues.append(ValidationIssue(severity=severity, path=path, message=message))


def _normalize_category_key(raw: str) -> str:
    text = raw.strip().lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _resolve_main_category(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    key = _normalize_category_key(str(raw))
    if key in MAIN_CATEGORIES:
        return key
    alias = LEGACY_MAIN_ALIASES.get(key)
    if alias and alias in MAIN_CATEGORIES:
        return alias
    if key in LEGACY_ONLY_MAIN:
        return key
    return None


def _looks_like_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_local_app(
    root: Path,
    *,
    strict: bool = False,
) -> ValidationReport:
    """Validate a local app workspace without calling the API."""
    issues: list[ValidationIssue] = []
    functions_count = 0
    webhooks_count = 0

    try:
        config = load_workspace(root)
    except Exception as exc:  # noqa: BLE001
        _issue(issues, "error", "caraer.json", f"Invalid workspace config: {exc}")
        return ValidationReport(
            ok=False,
            root=str(root),
            issues=issues,
        )

    manifest_path = app_manifest_path(root, config.srcDir)
    if not manifest_path.is_file():
        _issue(
            issues,
            "error",
            str(manifest_path.relative_to(root)),
            "Missing app manifest (app.caraer.yaml).",
        )
        return ValidationReport(ok=False, root=str(root), issues=issues, functions=0, webhooks=0)

    rel_manifest = str(manifest_path.relative_to(root))
    try:
        manifest = load_local_app(manifest_path)
    except Exception as exc:  # noqa: BLE001
        _issue(issues, "error", rel_manifest, f"Could not parse manifest: {exc}")
        return ValidationReport(ok=False, root=str(root), issues=issues)

    _validate_manifest(manifest, config, rel_manifest, issues)
    functions_count = _validate_functions(root, config, issues)
    webhooks_count = _validate_webhooks(root, config, issues)

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    ok = error_count == 0 and (not strict or warning_count == 0)
    return ValidationReport(
        ok=ok,
        root=str(root),
        issues=issues,
        functions=functions_count,
        webhooks=webhooks_count,
    )


def _validate_manifest(
    manifest: dict[str, Any],
    config: ProjectConfig,
    rel_manifest: str,
    issues: list[ValidationIssue],
) -> None:
    name = str(manifest.get("name") or "").strip()
    label = str(manifest.get("label") or "").strip()
    if not name:
        _issue(issues, "error", f"{rel_manifest}:name", "name is required.")
    if not label:
        _issue(issues, "error", f"{rel_manifest}:label", "label is required.")

    uuid = str(manifest.get("uuid") or "").strip()
    if uuid and not UUID_RE.match(uuid):
        _issue(issues, "error", f"{rel_manifest}:uuid", "uuid must be a valid UUID.")
    if config.appUuid and uuid and config.appUuid != uuid:
        _issue(
            issues,
            "warning",
            f"{rel_manifest}:uuid",
            f"Manifest uuid ({uuid}) differs from caraer.json appUuid ({config.appUuid}).",
        )

    auth = str(manifest.get("authMethod") or "").strip().upper()
    if not auth:
        _issue(issues, "error", f"{rel_manifest}:authMethod", "authMethod is required.")
    elif auth not in {"OAUTH2", "API_KEY"}:
        _issue(
            issues,
            "error",
            f"{rel_manifest}:authMethod",
            "authMethod must be OAUTH2 or API_KEY.",
        )
    elif auth == "OAUTH2":
        redirects = manifest.get("oauthRedirectUris")
        if not isinstance(redirects, list) or not any(
            isinstance(u, str) and u.strip() for u in redirects
        ):
            _issue(
                issues,
                "error",
                f"{rel_manifest}:oauthRedirectUris",
                "OAUTH2 apps require at least one oauthRedirectUris entry.",
            )
        else:
            for idx, uri in enumerate(redirects):
                if not isinstance(uri, str) or not _looks_like_url(uri.strip()):
                    _issue(
                        issues,
                        "error",
                        f"{rel_manifest}:oauthRedirectUris[{idx}]",
                        "Must be an http(s) URL.",
                    )

    runtime = str(manifest.get("runtime") or config.runtime or "").strip().lower()
    if config.is_app_platform_v2():
        if runtime not in {"nodejs22", "python312"}:
            _issue(
                issues,
                "error",
                f"{rel_manifest}:runtime",
                "platformVersion 2026.2 requires runtime nodejs22 or python312.",
            )
    elif runtime and runtime not in {"nodejs22", "python312"}:
        _issue(
            issues,
            "error",
            f"{rel_manifest}:runtime",
            "runtime must be nodejs22 or python312 when set.",
        )

    details = manifest.get("details")
    if details is None:
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details",
            "App details are required for public marketplace apps.",
        )
        return
    if not isinstance(details, dict):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details",
            "details must be an object.",
        )
        return

    category_raw = details.get("category")
    category = _resolve_main_category(str(category_raw) if category_raw is not None else None)
    if not category_raw or not str(category_raw).strip():
        _issue(issues, "error", f"{rel_manifest}:details.category", "category is required.")
    elif category is None:
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.category",
            f"Unknown category '{category_raw}'.",
        )

    brand = str(details.get("brandColor") or "").strip()
    if not brand:
        _issue(issues, "error", f"{rel_manifest}:details.brandColor", "brandColor is required.")
    elif not HEX_COLOR_RE.match(brand):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.brandColor",
            "brandColor must be a hex color like #E74363.",
        )

    text_color = str(details.get("textColor") or "").strip()
    if text_color and not HEX_COLOR_RE.match(text_color):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.textColor",
            "textColor must be a hex color like #FFFFFF.",
        )

    subs = details.get("subcategories")
    if subs is None:
        subs_list: list[str] = []
    elif not isinstance(subs, list):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.subcategories",
            "subcategories must be a list of strings.",
        )
        subs_list = []
    else:
        subs_list = [str(s).strip() for s in subs if s is not None and str(s).strip()]

    if category and category in MAIN_CATEGORIES:
        allowed = MAIN_CATEGORIES[category]
        invalid = [
            s for s in subs_list if _normalize_category_key(s) not in allowed
        ]
        if invalid:
            _issue(
                issues,
                "error",
                f"{rel_manifest}:details.subcategories",
                f"Invalid for '{category}': {', '.join(invalid)}.",
            )
        if not subs_list and category not in LEGACY_ONLY_MAIN:
            _issue(
                issues,
                "warning",
                f"{rel_manifest}:details.subcategories",
                "Select at least one subcategory for marketplace listing.",
            )

    description = str(details.get("description") or "").strip()
    if not description:
        _issue(
            issues,
            "warning",
            f"{rel_manifest}:details.description",
            "description is empty; required before marketplace submit.",
        )
    elif description.upper().startswith("TODO"):
        _issue(
            issues,
            "warning",
            f"{rel_manifest}:details.description",
            "description still looks like a placeholder (TODO…).",
        )

    url = str(details.get("url") or "").strip()
    if url and not _looks_like_url(url):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.url",
            "url must be an http(s) URL when set.",
        )

    image = str(details.get("image") or "").strip()
    if image and not _looks_like_url(image):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.image",
            "image must be an http(s) URL when set.",
        )


def _validate_functions(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    base = functions_dir(root, config.srcDir)
    if not base.is_dir():
        _issue(
            issues,
            "warning",
            str(base.relative_to(root)),
            "No functions directory found.",
        )
        return 0

    try:
        discovered = discover_local_functions(root, config)
    except Exception as exc:  # noqa: BLE001
        _issue(issues, "error", str(base.relative_to(root)), str(exc))
        return 0

    try:
        manifest_runtime = str(
            load_local_app(app_manifest_path(root, config.srcDir)).get("runtime") or ""
        ).strip().lower()
    except Exception:  # noqa: BLE001
        manifest_runtime = ""
    expected_runtime = manifest_runtime or str(config.resolved_runtime("") or "").strip().lower()

    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest_file = child / "function.caraer.json"
        if not manifest_file.is_file():
            _issue(
                issues,
                "error",
                str(manifest_file.relative_to(root)),
                "Missing function.caraer.json.",
            )

    for manifest, entry_path, _code in discovered:
        rel = f"functions/{manifest.name}"
        if manifest.name != entry_path.parent.name:
            _issue(
                issues,
                "warning",
                rel,
                f"function name '{manifest.name}' does not match folder '{entry_path.parent.name}'.",
            )
        if expected_runtime and config.is_app_platform_v2() and manifest.runtime != expected_runtime:
            _issue(
                issues,
                "warning",
                f"{rel}:runtime",
                f"Function runtime '{manifest.runtime}' differs from app runtime '{expected_runtime}'.",
            )
        if not entry_path.is_file():
            _issue(issues, "error", str(entry_path.relative_to(root)), "Missing entry file.")

    if not discovered:
        _issue(
            issues,
            "warning",
            str(base.relative_to(root)),
            "No local functions found.",
        )
    return len(discovered)


def _validate_webhooks(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    base = webhooks_dir(root, config.srcDir)
    if not base.is_dir():
        return 0

    function_names = set(list_local_function_names(root, config))
    try:
        local = discover_local_webhooks(root, config)
    except Exception as exc:  # noqa: BLE001
        _issue(issues, "error", str(base.relative_to(root)), f"Could not read webhooks: {exc}")
        return 0

    for path, item in local:
        rel = str(path.relative_to(root))
        topic = str(item.get("topic") or "").strip()
        if not topic:
            _issue(issues, "error", f"{rel}:topic", "topic is required.")

        mode = str(item.get("deliveryMode") or "").strip().upper()
        if not mode:
            _issue(issues, "error", f"{rel}:deliveryMode", "deliveryMode is required.")
        elif mode not in {"HTTP", "SERVERLESS"}:
            _issue(
                issues,
                "error",
                f"{rel}:deliveryMode",
                "deliveryMode must be HTTP or SERVERLESS.",
            )
        elif mode == "HTTP":
            url = str(item.get("url") or "").strip()
            if not url:
                _issue(issues, "error", f"{rel}:url", "HTTP webhooks require url.")
            elif not _looks_like_url(url):
                _issue(issues, "error", f"{rel}:url", "url must be an http(s) URL.")
        elif mode == "SERVERLESS":
            sf = item.get("serverlessFunction")
            if not isinstance(sf, dict) or not (sf.get("name") or sf.get("uuid")):
                _issue(
                    issues,
                    "error",
                    f"{rel}:serverlessFunction",
                    "SERVERLESS webhooks require serverlessFunction.name or .uuid.",
                )
            else:
                name = str(sf.get("name") or "").strip()
                if name and name not in function_names:
                    _issue(
                        issues,
                        "error",
                        f"{rel}:serverlessFunction.name",
                        f"Unknown local function '{name}'.",
                    )

        uuid = str(item.get("uuid") or "").strip()
        if uuid and not UUID_RE.match(uuid):
            _issue(issues, "error", f"{rel}:uuid", "uuid must be a valid UUID.")

    return len(local)
