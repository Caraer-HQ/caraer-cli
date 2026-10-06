"""Local validation for Caraer app workspaces (manifest, functions, webhooks, schedules, inbound)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from caraer_cli.local_app import load_local_app
from caraer_cli.project.inbound_sync import discover_local_inbound
from caraer_cli.project.paths import (
    app_manifest_path,
    functions_dir,
    inbound_dir,
    schedules_dir,
    webhooks_dir,
)
from caraer_cli.project.modules_codegen import generate_module_types
from caraer_cli.project.scaffold import ensure_package_json, ensure_tsconfig
from caraer_cli.project.modules_sync import (
    DISALLOWED_MODULE_FIELD_TYPES,
    JSX_FRAMEWORKS,
    MODULE_CATEGORIES,
    MODULE_FIELD_TYPES,
    MODULE_KINDS,
    PINNED_FRAMEWORK_MAJORS,
    discover_local_modules,
    is_module_field_group,
    parse_major,
)
from caraer_cli.project.schedules_sync import discover_local_schedules
from caraer_cli.project.schema import PLATFORM_VERSION_V2, ProjectConfig, load_workspace
from caraer_cli.project.settings_sections_sync import discover_local_settings_sections
from caraer_cli.project.settings_sync import discover_local_settings
from caraer_cli.project.app_bars_sync import discover_local_app_bars
from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS, discover_local_lifecycle
from caraer_cli.project.marketplace_assemble import assemble_local_manifest
from caraer_cli.project.naming import MODULE_NAME_RE as SETTING_FIELD_NAME_RE
from caraer_cli.project.sync import discover_local_functions, list_local_function_names
from caraer_cli.project.webhooks_sync import discover_local_webhooks

Severity = Literal["error", "warning"]

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# 5–6 field cron (backend accepts both); keep loose.
CRON_RE = re.compile(r"^(\S+\s+){4,5}\S+$")
INBOUND_AUTH_MODES = frozenset(
    {"NONE", "SHARED_SECRET", "INSTALLATION_TOKEN", "GOOGLE_OIDC", "GOOGLE_CALENDAR_CHANNEL"}
)
SETTING_FIELD_TYPES = frozenset(
    {
        "SINGLE_LINE",
        "MULTI_LINE",
        "SINGLE_SELECT",
        "MULTI_SELECT",
        "RECORD_SINGLE_SELECT",
        "RECORD_MULTI_SELECT",
        "OBJECT_SINGLE_SELECT",
        "OBJECT_MULTI_SELECT",
        "PROPERTY_SINGLE_SELECT",
        "PROPERTY_MULTI_SELECT",
        "SWITCH",
        "MAPPING",
        "FILE",
        "MULTI_FILE",
        "IMAGE",
        "COLOR",
        "SECRET",
        "ACTION",
        "REPEATABLE",
    }
)
SELECT_FIELD_TYPES = frozenset(
    {
        "SINGLE_SELECT",
        "MULTI_SELECT",
    }
)
OBJECT_SELECT_FIELD_TYPES = frozenset(
    {
        "OBJECT_SINGLE_SELECT",
        "OBJECT_MULTI_SELECT",
    }
)
PROPERTY_SELECT_FIELD_TYPES = frozenset(
    {
        "PROPERTY_SINGLE_SELECT",
        "PROPERTY_MULTI_SELECT",
    }
)
CONDITION_OPERATORS = frozenset(
    {"EQUALS", "NOT_EQUALS", "IN", "NOT_IN", "IS_SET", "IS_NOT_SET"}
)
VALUELESS_CONDITION_OPERATORS = frozenset({"IS_SET", "IS_NOT_SET"})
LIST_CONDITION_OPERATORS = frozenset({"IN", "NOT_IN"})
APP_BAR_LOCATIONS = frozenset(
    {
        "RECORD_PREVIEW",
        "RECORD_OVERVIEW",
        "RECORD_DETAIL",
        "TOOL_BAR",
        "TRAIT_BAR",
        "RECORD_TRAIT",
    }
)
ACTION_BASED_LOCATIONS = frozenset(
    {"RECORD_PREVIEW", "RECORD_OVERVIEW", "RECORD_TRAIT"}
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
    schedules: int = 0
    inbound: int = 0
    oauth_providers: int = 0
    settings: int = 0
    app_bars: int = 0
    lifecycle_hooks: int = 0
    modules: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "root": self.root,
            "functions": self.functions,
            "webhooks": self.webhooks,
            "schedules": self.schedules,
            "inbound": self.inbound,
            "oauthProviders": self.oauth_providers,
            "settings": self.settings,
            "appBars": self.app_bars,
            "lifecycleHooks": self.lifecycle_hooks,
            "modules": self.modules,
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


def _looks_like_svg_url(value: str) -> bool:
    if not _looks_like_url(value):
        return False
    path = urlparse(value).path.lower()
    return path.endswith(".svg")


def _require_svg_url(
    issues: list[ValidationIssue],
    rel_manifest: str,
    field: str,
    value: object,
    *,
    required_message: str,
) -> None:
    text = str(value or "").strip()
    if not text:
        _issue(issues, "error", f"{rel_manifest}:{field}", required_message)
        return
    if not _looks_like_url(text):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:{field}",
            f"{field.split('.')[-1]} must be an http(s) URL.",
        )
        return
    if not _looks_like_svg_url(text):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:{field}",
            f"{field.split('.')[-1]} must be an SVG URL.",
        )


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

    if config.platformVersion == PLATFORM_VERSION_V2:
        _issue(
            issues,
            "warning",
            "caraer.json",
            "This app is 2026.2. Run 'caraer apps upgrade' or accept the "
            "default-yes prompt on the next 'caraer apps push' to rewrite "
            "it to 2026.2.1.",
        )
    _validate_manifest(manifest, config, rel_manifest, issues)
    functions_count = _validate_functions(root, config, issues)
    webhooks_count = _validate_webhooks(root, config, issues)
    schedules_count = _validate_schedules(root, config, issues)
    inbound_count = _validate_inbound(root, config, issues)
    oauth_count = _validate_oauth_providers(manifest, rel_manifest, issues)
    function_names = set(list_local_function_names(root, config))
    settings_count = _validate_settings(
        root, config, manifest, rel_manifest, function_names, issues
    )
    _validate_settings_sections(root, config, manifest, issues)
    app_bars_count = _validate_app_bars(
        root, config, manifest, rel_manifest, function_names, issues
    )
    lifecycle_count = _validate_lifecycle(
        root, config, function_names, issues
    )
    modules_count = _validate_modules(root, config, issues)
    _validate_against_json_schemas(root, config, issues)

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    ok = error_count == 0 and (not strict or warning_count == 0)
    return ValidationReport(
        ok=ok,
        root=str(root),
        issues=issues,
        functions=functions_count,
        webhooks=webhooks_count,
        schedules=schedules_count,
        inbound=inbound_count,
        oauth_providers=oauth_count,
        settings=settings_count,
        app_bars=app_bars_count,
        lifecycle_hooks=lifecycle_count,
        modules=modules_count,
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

    if not config.privateApp:
        _require_svg_url(
            issues,
            rel_manifest,
            "brandmark",
            manifest.get("brandmark"),
            required_message="brandmark is required.",
        )
    elif manifest.get("brandmark"):
        _require_svg_url(
            issues,
            rel_manifest,
            "brandmark",
            manifest.get("brandmark"),
            required_message="brandmark is required.",
        )

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
        if config.privateApp:
            return
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

    require_listing = not config.privateApp
    category_raw = details.get("category")
    category = _resolve_main_category(str(category_raw) if category_raw is not None else None)
    if (not category_raw or not str(category_raw).strip()) and require_listing:
        _issue(issues, "error", f"{rel_manifest}:details.category", "category is required.")
    elif category_raw and category is None:
        _issue(
            issues,
            "error",
            f"{rel_manifest}:details.category",
            f"Unknown category '{category_raw}'.",
        )

    brand = str(details.get("brandColor") or "").strip()
    if not brand and require_listing:
        _issue(issues, "error", f"{rel_manifest}:details.brandColor", "brandColor is required.")
    elif brand and not HEX_COLOR_RE.match(brand):
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
        if require_listing and not subs_list and category not in LEGACY_ONLY_MAIN:
            _issue(
                issues,
                "warning",
                f"{rel_manifest}:details.subcategories",
                "Select at least one subcategory for marketplace listing.",
            )

    description = str(details.get("description") or "").strip()
    if require_listing and not description:
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

    if require_listing or details.get("image"):
        _require_svg_url(
            issues,
            rel_manifest,
            "details.image",
            details.get("image"),
            required_message="image is required.",
        )


def _validate_functions(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    base = functions_dir(root, config.srcDir)
    if not base.is_dir():
        # An app that only ships CMS modules has no runtime code to deploy, so
        # a missing functions directory is expected rather than suspicious.
        if not discover_local_modules(root, config):
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

    if not config.is_layout_v21():
        # function.caraer.json is optional: a folder with an entry file (index.js /
        # main.py) is discovered by convention. Only flag folders that are neither.
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            has_manifest = (child / "function.caraer.json").is_file()
            has_entry = (child / "index.js").is_file() or (child / "main.py").is_file()
            if not has_manifest and not has_entry:
                _issue(
                    issues,
                    "error",
                    str(child.relative_to(root)),
                    "Not a function: add index.js/main.py or a function.caraer.json with an entry.",
                )

    seen_function_names: set[str] = set()
    for manifest, entry_path, _code, _source_files in discovered:
        rel = str(entry_path.relative_to(root)) if config.is_layout_v21() else f"functions/{manifest.name}"
        if manifest.name in seen_function_names:
            _issue(issues, "error", rel, f"Function name '{manifest.name}' is used more than once.")
        seen_function_names.add(manifest.name)
        if not config.is_layout_v21() and manifest.name != entry_path.parent.name:
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

    _validate_shared(root, config, issues)
    return len(discovered)


def _validate_shared(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> None:
    from caraer_cli.project.paths import shared_dir

    shared = shared_dir(root, config.srcDir)
    if not shared.is_dir():
        return
    has_files = any(path.is_file() for path in shared.rglob("*"))
    if has_files and not config.is_app_platform_v2():
        _issue(
            issues,
            "warning",
            str(shared.relative_to(root)),
            "src/app/shared/ requires platformVersion 2026.2; "
            "V1 functions cannot import shared files.",
        )


def _validate_webhooks(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    base = webhooks_dir(root, config.srcDir)
    function_names = set(list_local_function_names(root, config))
    try:
        local = discover_local_webhooks(root, config)
    except Exception as exc:  # noqa: BLE001
        _issue(
            issues,
            "error",
            str(base.relative_to(root)) if base.is_dir() else "src/app",
            f"Could not read webhooks: {exc}",
        )
        return 0
    if not local:
        return 0

    seen_topics: set[str] = set()
    for path, item in local:
        rel = str(path.relative_to(root))
        topic = str(item.get("topic") or "").strip()
        if not topic:
            _issue(issues, "error", f"{rel}:topic", "topic is required.")
        elif topic in seen_topics:
            _issue(issues, "error", f"{rel}:topic", f"Topic '{topic}' is declared more than once.")
        else:
            seen_topics.add(topic)

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


def _function_ref_ok(sf: Any, function_names: set[str], issues: list[ValidationIssue], rel: str) -> None:
    if not isinstance(sf, dict) or not (sf.get("name") or sf.get("uuid")):
        _issue(
            issues,
            "error",
            f"{rel}:serverlessFunction",
            "Requires serverlessFunction.name or .uuid.",
        )
        return
    name = str(sf.get("name") or "").strip()
    if name and name not in function_names:
        _issue(
            issues,
            "error",
            f"{rel}:serverlessFunction.name",
            f"Unknown local function '{name}'.",
        )


def _validate_schedules(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    base = schedules_dir(root, config.srcDir)
    if not base.is_dir():
        return 0
    function_names = set(list_local_function_names(root, config))
    try:
        local = discover_local_schedules(root, config)
    except Exception as exc:  # noqa: BLE001
        _issue(issues, "error", str(base.relative_to(root)), f"Could not read schedules: {exc}")
        return 0

    for path, item in local:
        rel = str(path.relative_to(root))
        name = str(item.get("name") or "").strip()
        if not name:
            _issue(issues, "error", f"{rel}:name", "name is required.")
        schedule = str(item.get("schedule") or "").strip()
        if not schedule:
            _issue(issues, "error", f"{rel}:schedule", "schedule (cron) is required.")
        elif not CRON_RE.match(schedule):
            _issue(
                issues,
                "warning",
                f"{rel}:schedule",
                "schedule does not look like a 5–6 field cron expression.",
            )
        _function_ref_ok(item.get("serverlessFunction"), function_names, issues, rel)
        uuid = str(item.get("uuid") or "").strip()
        if uuid and not UUID_RE.match(uuid):
            _issue(issues, "error", f"{rel}:uuid", "uuid must be a valid UUID.")
    return len(local)


def _validate_inbound(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    base = inbound_dir(root, config.srcDir)
    if not base.is_dir():
        return 0
    function_names = set(list_local_function_names(root, config))
    try:
        local = discover_local_inbound(root, config)
    except Exception as exc:  # noqa: BLE001
        _issue(issues, "error", str(base.relative_to(root)), f"Could not read inbound: {exc}")
        return 0

    for path, item in local:
        rel = str(path.relative_to(root))
        name = str(item.get("name") or "").strip()
        if not name:
            _issue(issues, "error", f"{rel}:name", "name is required.")
        auth = str(item.get("authMode") or "NONE").strip().upper()
        if auth not in INBOUND_AUTH_MODES:
            _issue(
                issues,
                "error",
                f"{rel}:authMode",
                f"authMode must be one of: {', '.join(sorted(INBOUND_AUTH_MODES))}.",
            )
        elif auth == "SHARED_SECRET" and not str(item.get("sharedSecret") or "").strip():
            if not item.get("hasSharedSecret"):
                _issue(
                    issues,
                    "warning",
                    f"{rel}:sharedSecret",
                    "SHARED_SECRET inbound routes should set sharedSecret before push.",
                )
        _function_ref_ok(item.get("serverlessFunction"), function_names, issues, rel)
        uuid = str(item.get("uuid") or "").strip()
        if uuid and not UUID_RE.match(uuid):
            _issue(issues, "error", f"{rel}:uuid", "uuid must be a valid UUID.")
    return len(local)


def _validate_oauth_providers(
    manifest: dict[str, Any],
    rel_manifest: str,
    issues: list[ValidationIssue],
) -> int:
    providers = manifest.get("externalOAuthProviders") or []
    if providers is None:
        return 0
    if not isinstance(providers, list):
        _issue(
            issues,
            "error",
            f"{rel_manifest}:externalOAuthProviders",
            "externalOAuthProviders must be a list.",
        )
        return 0

    for idx, item in enumerate(providers):
        rel = f"{rel_manifest}:externalOAuthProviders[{idx}]"
        if not isinstance(item, dict):
            _issue(issues, "error", rel, "Provider must be an object.")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            _issue(issues, "error", f"{rel}:name", "name is required.")
        if item.get("preset") is not None and str(item.get("preset") or "").strip():
            _issue(
                issues,
                "warning",
                f"{rel}:preset",
                "preset is deprecated and ignored; set authorizeUrl and tokenUrl explicitly.",
            )
        for url_key in ("authorizeUrl", "tokenUrl"):
            url = str(item.get(url_key) or "").strip()
            if not url:
                _issue(
                    issues,
                    "error",
                    f"{rel}:{url_key}",
                    f"{url_key} is required.",
                )
            elif not url.startswith("${") and not _looks_like_url(url):
                _issue(
                    issues,
                    "error",
                    f"{rel}:{url_key}",
                    f"{url_key} must be an http(s) URL.",
                )
        owner = str(item.get("connectionOwner") or "").strip().upper()
        if owner and owner not in ("COMPANY", "USER"):
            _issue(
                issues,
                "error",
                f"{rel}:connectionOwner",
                "connectionOwner must be COMPANY or USER.",
            )
        logo = str(item.get("logo") or "").strip()
        if not logo:
            _issue(
                issues,
                "warning",
                f"{rel}:logo",
                "logo is recommended for the Connect button (http(s) image URL).",
            )
        elif not logo.startswith("${") and not _looks_like_url(logo):
            _issue(
                issues,
                "error",
                f"{rel}:logo",
                "logo must be an http(s) URL.",
            )
        client_id = str(item.get("clientId") or "").strip()
        if not client_id:
            _issue(
                issues,
                "warning",
                f"{rel}:clientId",
                "clientId is empty; provider will be skipped on push.",
            )
        scopes = item.get("scopes")
        if scopes is not None and not isinstance(scopes, list):
            _issue(
                issues,
                "error",
                f"{rel}:scopes",
                "scopes must be a list of strings.",
            )
        uuid = str(item.get("uuid") or "").strip()
        if uuid and not UUID_RE.match(uuid):
            _issue(issues, "error", f"{rel}:uuid", "uuid must be a valid UUID.")
    return len(providers)


def _merged_settings(
    root: Path, config: ProjectConfig, manifest: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    assembled = assemble_local_manifest(
        root, config, manifest, resolve_functions=False, strict_function_refs=False
    )
    items = assembled.get("settingsSchema") or []
    out: list[tuple[str, dict[str, Any]]] = []
    file_by_name = {
        str(item.get("name") or ""): path
        for path, item in discover_local_settings(root, config)
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        path = file_by_name.get(name)
        rel = (
            str(path.relative_to(root))
            if path is not None
            else "app.caraer.yaml:settingsSchema"
        )
        out.append((rel, item))
    return out


def _validate_settings(
    root: Path,
    config: ProjectConfig,
    manifest: dict[str, Any],
    rel_manifest: str,
    function_names: set[str],
    issues: list[ValidationIssue],
) -> int:
    rows = _merged_settings(root, config, manifest)
    known_names = {
        str(item.get("name") or "").strip()
        for _rel, item in rows
        if str(item.get("name") or "").strip()
    }
    action_names = {
        str(item.get("name") or "").strip()
        for _rel, item in rows
        if str(item.get("type") or "").strip().upper() == "ACTION"
        and str(item.get("name") or "").strip()
    }
    seen: set[str] = set()
    for rel, item in rows:
        name = str(item.get("name") or "").strip()
        if not name:
            _issue(issues, "error", f"{rel}:name", "name is required.")
            continue
        key = name.lower()
        if key in seen:
            _issue(issues, "error", f"{rel}:name", f"Duplicate setting name '{name}'.")
        seen.add(key)
        _validate_visible_when(item, name, known_names, action_names, rel, issues)
        _validate_filter_traits(item, rel, issues)
        _validate_property_filters(item, rel, issues)
        value_scope = str(item.get("valueScope") or "").strip().upper()
        if value_scope and value_scope not in ("COMPANY", "USER"):
            _issue(
                issues,
                "error",
                f"{rel}:valueScope",
                "valueScope must be COMPANY or USER.",
            )
        field_type = str(item.get("type") or "").strip().upper()
        if not field_type:
            _issue(issues, "error", f"{rel}:type", "type is required.")
        elif field_type not in SETTING_FIELD_TYPES:
            _issue(
                issues,
                "error",
                f"{rel}:type",
                f"Unknown type '{field_type}'.",
            )
        elif field_type in SELECT_FIELD_TYPES:
            options = item.get("options")
            options_source = item.get("optionsSource")
            if not options and not options_source:
                _issue(
                    issues,
                    "error",
                    f"{rel}:options",
                    "SELECT fields require options or optionsSource.",
                )
        elif field_type == "ACTION":
            if item.get("required") is True:
                _issue(
                    issues,
                    "error",
                    f"{rel}:required",
                    "ACTION fields cannot be required.",
                )
            _validate_action_source(item, rel, function_names, issues)
    return len(rows)


def _merged_settings_sections(
    root: Path, config: ProjectConfig, manifest: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    assembled = assemble_local_manifest(
        root, config, manifest, resolve_functions=False, strict_function_refs=False
    )
    items = assembled.get("settingsSections") or []
    out: list[tuple[str, dict[str, Any]]] = []
    file_by_title = {
        str(item.get("title") or "").strip().lower(): path
        for path, item in discover_local_settings_sections(root, config)
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        path = file_by_title.get(title.lower())
        rel = (
            str(path.relative_to(root))
            if path is not None
            else "app.caraer.yaml:settingsSections"
        )
        out.append((rel, item))
    return out


def _validate_settings_sections(
    root: Path,
    config: ProjectConfig,
    manifest: dict[str, Any],
    issues: list[ValidationIssue],
) -> int:
    rows = _merged_settings_sections(root, config, manifest)
    if not rows:
        return 0
    known_names = {
        str(item.get("name") or "").strip()
        for _rel, item in _merged_settings(root, config, manifest)
        if str(item.get("name") or "").strip()
    }
    assigned: set[str] = set()
    for rel, item in rows:
        title = str(item.get("title") or "").strip()
        if not title:
            _issue(issues, "error", f"{rel}:title", "title is required.")
        settings = item.get("settings")
        if not isinstance(settings, list) or not settings:
            _issue(
                issues,
                "error",
                f"{rel}:settings",
                "settings must be a non-empty list of settingsSchema field names.",
            )
            continue
        for index, raw in enumerate(settings):
            name = str(raw or "").strip()
            where = f"{rel}:settings[{index}]"
            if not name:
                _issue(issues, "error", where, "Setting name is required.")
                continue
            if name not in known_names:
                _issue(
                    issues,
                    "error",
                    where,
                    f"Setting '{name}' is not defined in settingsSchema.",
                )
            key = name.lower()
            if key in assigned:
                _issue(
                    issues,
                    "error",
                    where,
                    f"Setting '{name}' is assigned to more than one settings section.",
                )
            assigned.add(key)
    for setting_rel, item in _merged_settings(root, config, manifest):
        name = str(item.get("name") or "").strip()
        if name and name.lower() not in assigned:
            _issue(
                issues,
                "warning",
                f"{setting_rel}:name",
                f"Setting '{name}' is not assigned to a settings section "
                "and will appear under Other settings.",
            )
    return len(rows)


def _validate_action_source(
    item: dict[str, Any],
    rel: str,
    function_names: set[str],
    issues: list[ValidationIssue],
) -> None:
    source = item.get("actionSource")
    if not isinstance(source, dict):
        _issue(
            issues,
            "error",
            f"{rel}:actionSource",
            "ACTION fields require actionSource with a serverless function name.",
        )
        return
    source_type = str(source.get("type") or "").strip().upper()
    if source_type and source_type != "SERVERLESS":
        _issue(
            issues,
            "error",
            f"{rel}:actionSource.type",
            "actionSource.type must be SERVERLESS.",
        )
    fn_name = str(source.get("serverlessFunctionName") or "").strip()
    fn_uuid = str(source.get("serverlessFunctionUuid") or "").strip()
    if not fn_name and not fn_uuid:
        _issue(
            issues,
            "error",
            f"{rel}:actionSource.serverlessFunctionName",
            "actionSource must set serverlessFunctionName or serverlessFunctionUuid.",
        )
    elif fn_name and fn_name not in function_names:
        _issue(
            issues,
            "error",
            f"{rel}:actionSource.serverlessFunctionName",
            f"Unknown local function '{fn_name}'.",
        )


def _validate_filter_traits(
    item: dict[str, Any],
    rel: str,
    issues: list[ValidationIssue],
) -> None:
    """Validate the object-picker trait filter on one settings field."""
    traits = item.get("filterTraits")
    if traits is None:
        return
    where = f"{rel}:filterTraits"
    if not isinstance(traits, list):
        _issue(issues, "error", where, "filterTraits must be a list of trait names.")
        return

    field_type = str(item.get("type") or "").strip().upper()
    if field_type and field_type not in OBJECT_SELECT_FIELD_TYPES:
        _issue(
            issues,
            "error",
            where,
            "filterTraits only applies to OBJECT_SINGLE_SELECT and "
            "OBJECT_MULTI_SELECT fields.",
        )
        return

    for index, trait in enumerate(traits):
        if not isinstance(trait, str) or not trait.strip():
            _issue(
                issues,
                "error",
                f"{where}[{index}]",
                "Each filterTraits entry must be a non-empty trait name.",
            )


def _validate_property_filters(
    item: dict[str, Any],
    rel: str,
    issues: list[ValidationIssue],
) -> None:
    """Validate property type/format filters on one settings or module field."""
    _validate_property_filter_list(
        item,
        rel,
        issues,
        canonical="filterPropertyTypes",
        alias="allowedPropertyTypes",
        noun="type",
    )
    _validate_property_filter_list(
        item,
        rel,
        issues,
        canonical="filterPropertyFormats",
        alias="allowedPropertyFormats",
        noun="format",
    )


def _validate_property_filter_list(
    item: dict[str, Any],
    rel: str,
    issues: list[ValidationIssue],
    *,
    canonical: str,
    alias: str,
    noun: str,
) -> None:
    values = item.get(canonical)
    used = canonical
    if values is None:
        values = item.get(alias)
        used = alias
    if values is None:
        return
    where = f"{rel}:{used}"
    if not isinstance(values, list):
        _issue(issues, "error", where, f"{used} must be a list of property {noun} names.")
        return

    field_type = str(item.get("type") or "").strip().upper()
    if field_type and field_type not in PROPERTY_SELECT_FIELD_TYPES:
        _issue(
            issues,
            "error",
            where,
            f"{used} only applies to PROPERTY_SINGLE_SELECT and "
            "PROPERTY_MULTI_SELECT fields.",
        )
        return

    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            _issue(
                issues,
                "error",
                f"{where}[{index}]",
                f"Each {used} entry must be a non-empty property {noun} name.",
            )


def _validate_visible_when(
    item: dict[str, Any],
    name: str,
    known_names: set[str],
    action_names: set[str],
    rel: str,
    issues: list[ValidationIssue],
) -> None:
    """Validate conditional visibility rules on one settings field."""
    conditions = item.get("visibleWhen")
    if conditions is None:
        return
    if not isinstance(conditions, list):
        _issue(issues, "error", f"{rel}:visibleWhen", "visibleWhen must be a list.")
        return

    for index, condition in enumerate(conditions):
        where = f"{rel}:visibleWhen[{index}]"
        if not isinstance(condition, dict):
            _issue(issues, "error", where, "Each visibleWhen entry must be an object.")
            continue

        field = str(condition.get("field") or "").strip()
        if not field:
            _issue(issues, "error", f"{where}.field", "field is required.")
        elif field == name:
            _issue(
                issues,
                "error",
                f"{where}.field",
                f"field '{field}' cannot reference the field itself.",
            )
        elif field not in known_names:
            _issue(
                issues,
                "error",
                f"{where}.field",
                f"Unknown field '{field}'; must match another setting name.",
            )
        elif field in action_names:
            _issue(
                issues,
                "error",
                f"{where}.field",
                f"field '{field}' is an ACTION button and cannot control visibility.",
            )

        operator = str(condition.get("operator") or "EQUALS").strip().upper()
        if operator not in CONDITION_OPERATORS:
            _issue(
                issues,
                "error",
                f"{where}.operator",
                f"operator must be one of: {', '.join(sorted(CONDITION_OPERATORS))}.",
            )
            continue

        has_value = "value" in condition and condition.get("value") is not None
        if operator not in VALUELESS_CONDITION_OPERATORS and not has_value:
            _issue(
                issues,
                "error",
                f"{where}.value",
                f"operator {operator} requires a value.",
            )
        if (
            operator in LIST_CONDITION_OPERATORS
            and has_value
            and not isinstance(condition.get("value"), list)
        ):
            _issue(
                issues,
                "error",
                f"{where}.value",
                f"operator {operator} requires a list of values.",
            )


def _validate_app_bars(
    root: Path,
    config: ProjectConfig,
    manifest: dict[str, Any],
    rel_manifest: str,
    function_names: set[str],
    issues: list[ValidationIssue],
) -> int:
    assembled = assemble_local_manifest(
        root, config, manifest, resolve_functions=False, strict_function_refs=False
    )
    items = assembled.get("appBars") or []
    file_by_id = {
        f"{str(i.get('location') or '').upper()}|{str(i.get('label') or '').lower()}": p
        for p, i in discover_local_app_bars(root, config)
    }
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        count += 1
        location = str(item.get("location") or "").strip().upper()
        label = str(item.get("label") or "").strip()
        key = f"{location}|{label.lower()}"
        path = file_by_id.get(key)
        rel = (
            str(path.relative_to(root))
            if path is not None
            else f"{rel_manifest}:appBars"
        )
        if not label:
            _issue(issues, "error", f"{rel}:label", "label is required.")
        if location not in APP_BAR_LOCATIONS:
            _issue(
                issues,
                "error",
                f"{rel}:location",
                f"location must be one of: {', '.join(sorted(APP_BAR_LOCATIONS))}.",
            )
            continue
        if location in ACTION_BASED_LOCATIONS:
            webhook = item.get("webhook")
            if not isinstance(webhook, dict):
                _issue(
                    issues,
                    "warning",
                    f"{rel}:webhook",
                    "Action app bars usually define a webhook.",
                )
            else:
                _validate_sf_ref(
                    webhook.get("serverlessFunction"),
                    function_names,
                    issues,
                    f"{rel}:webhook",
                )
        else:
            iframe = str(item.get("iframeUrl") or "").strip()
            if not iframe:
                _issue(
                    issues,
                    "error",
                    f"{rel}:iframeUrl",
                    "Iframe app bars require iframeUrl.",
                )
            elif not iframe.startswith("${") and not _looks_like_url(iframe):
                _issue(
                    issues,
                    "error",
                    f"{rel}:iframeUrl",
                    "iframeUrl must be an http(s) URL.",
                )
        if item.get("settingsSchema") is not None:
            _validate_app_bar_settings(
                item.get("settingsSchema"),
                f"{rel}:settingsSchema",
                function_names,
                issues,
            )
    return count


def _validate_app_bar_settings(
    fields: Any,
    rel: str,
    function_names: set[str],
    issues: list[ValidationIssue],
) -> None:
    """Validate one app-bar dialog schema the same way as installation settings."""
    if not isinstance(fields, list):
        _issue(issues, "error", rel, "settingsSchema must be a list.")
        return
    known_names = {
        str(item.get("name") or "").strip()
        for item in fields
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    action_names = {
        str(item.get("name") or "").strip()
        for item in fields
        if isinstance(item, dict)
        and str(item.get("type") or "").strip().upper() == "ACTION"
        and str(item.get("name") or "").strip()
    }
    seen: set[str] = set()
    for index, item in enumerate(fields):
        where = f"{rel}[{index}]"
        if not isinstance(item, dict):
            _issue(issues, "error", where, "Each settings field must be an object.")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            _issue(issues, "error", f"{where}:name", "name is required.")
            continue
        key = name.lower()
        if key in seen:
            _issue(issues, "error", f"{where}:name", f"Duplicate setting name '{name}'.")
        seen.add(key)
        _validate_visible_when(item, name, known_names, action_names, where, issues)
        _validate_filter_traits(item, where, issues)
        _validate_property_filters(item, where, issues)
        field_type = str(item.get("type") or "").strip().upper()
        if not field_type:
            _issue(issues, "error", f"{where}:type", "type is required.")
            continue
        if field_type not in SETTING_FIELD_TYPES:
            _issue(
                issues,
                "error",
                f"{where}:type",
                f"Unknown type '{field_type}'.",
            )
            continue
        if field_type in SELECT_FIELD_TYPES:
            options = item.get("options")
            options_source = item.get("optionsSource")
            if not options and not options_source:
                _issue(
                    issues,
                    "error",
                    f"{where}:options",
                    "SELECT fields require options or optionsSource.",
                )
            if isinstance(options_source, dict):
                fn_name = str(options_source.get("serverlessFunctionName") or "").strip()
                if fn_name and fn_name not in function_names:
                    _issue(
                        issues,
                        "error",
                        f"{where}:optionsSource.serverlessFunctionName",
                        f"Unknown local function '{fn_name}'.",
                    )
        elif field_type == "ACTION":
            if item.get("required") is True:
                _issue(
                    issues,
                    "error",
                    f"{where}:required",
                    "ACTION fields cannot be required.",
                )
            _validate_action_source(item, where, function_names, issues)
        elif field_type == "REPEATABLE":
            children = item.get("itemFields")
            if not isinstance(children, list) or not children:
                _issue(
                    issues,
                    "error",
                    f"{where}:itemFields",
                    "REPEATABLE fields require itemFields.",
                )
            else:
                _validate_app_bar_settings(
                    children,
                    f"{where}:itemFields",
                    function_names,
                    issues,
                )


def _validate_sf_ref(
    sf: Any,
    function_names: set[str],
    issues: list[ValidationIssue],
    rel: str,
) -> None:
    if not isinstance(sf, dict):
        return
    name = str(sf.get("name") or "").strip()
    if name and name not in function_names:
        _issue(
            issues,
            "error",
            f"{rel}:serverlessFunction",
            f"Unknown local function '{name}'.",
        )


def _validate_modules(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> int:
    """Validate CMS v2 modules and regenerate their TypeScript declarations."""
    modules = discover_local_modules(root, config)
    if not modules:
        return 0

    seen_names: set[str] = set()

    for module in modules:
        rel_dir = str(module.directory.relative_to(root))
        rel_config = str(module.entry.relative_to(root))

        if not module.entry.is_file():
            _issue(
                issues,
                "error",
                rel_dir,
                "Missing module .astro file. A module's entry point must be an .astro file, "
                "because Astro can only apply client:* directives to components it "
                "resolves statically.",
            )
            continue

        if module.legacy_config_path.is_file():
            _issue(
                issues,
                "error",
                str(module.legacy_config_path.relative_to(root)),
                "A module is one file now. Move this into "
                "`export const manifest = {...}` in the module .astro file and delete it.",
            )

        if module.error:
            _issue(issues, "error", rel_config, module.error)
            continue

        declared = str(module.config.get("name") or "").strip()
        if not declared:
            _issue(issues, "error", rel_config, "Module manifest is missing 'name'.")
        elif declared != module.name:
            _issue(
                issues,
                "error",
                rel_config,
                f"name '{declared}' must match the directory name '{module.name}'.",
            )
        elif not SETTING_FIELD_NAME_RE.match(declared):
            _issue(
                issues,
                "error",
                rel_config,
                f"name '{declared}' must be snake_case (a-z, 0-9, underscore).",
            )
        elif declared in seen_names:
            _issue(issues, "error", rel_config, f"Duplicate module name '{declared}'.")
        else:
            seen_names.add(declared)

        if not str(module.config.get("label") or "").strip():
            _issue(issues, "error", rel_config, "Module manifest is missing 'label'.")

        kind = str(module.config.get("kind") or "").strip()
        if not kind:
            _issue(issues, "error", rel_config, "Module manifest is missing 'kind'.")
        elif kind not in MODULE_KINDS:
            _issue(
                issues,
                "error",
                rel_config,
                f"kind '{kind}' is not one of {sorted(MODULE_KINDS)}.",
            )

        # A fixed set, so the same kind of block lands in the same group of the
        # library picker whichever app shipped it.
        category = str(module.config.get("category") or "").strip()
        if not category:
            _issue(
                issues,
                "error",
                rel_config,
                f"Module manifest is missing 'category'. One of {sorted(MODULE_CATEGORIES)}.",
            )
        elif category not in MODULE_CATEGORIES:
            _issue(
                issues,
                "error",
                rel_config,
                f"category '{category}' is not one of {sorted(MODULE_CATEGORIES)}.",
            )

        if module.config.get("components") is not None:
            _issue(
                issues,
                "error",
                rel_config,
                "Do not use 'components'. Put groups in fields as "
                '{ group: "Style", fields: [...] }.',
            )

        _validate_module_fields(module, rel_config, issues)
        _validate_module_frameworks(module, rel_dir, rel_config, issues)

    # Types are only worth writing once the shape is known to be sound.
    if not any(i.severity == "error" and "modules/" in i.path for i in issues):
        generate_module_types(root, config)
        if modules:
            ensure_tsconfig(root)
            ensure_package_json(root, config.name or root.name)

    return len(modules)


def _validate_module_fields(
    module: Any,
    rel_config: str,
    issues: list[ValidationIssue],
) -> None:
    field_names: set[str] = set()

    for item in module.fields:
        if is_module_field_group(item):
            title = str(item.get("group") or "").strip()
            if not title:
                _issue(issues, "error", rel_config, "A field group is missing 'group'.")
            nested = item.get("fields") or []
            if not nested:
                _issue(
                    issues,
                    "error",
                    rel_config,
                    f"Field group '{title or '?'}' has no fields.",
                )
            if item.get("name") or item.get("type"):
                _issue(
                    issues,
                    "error",
                    rel_config,
                    f"Field group '{title}' is not a field. Put name and type on the fields inside it.",
                )
            for child in nested:
                if not isinstance(child, dict):
                    _issue(
                        issues,
                        "error",
                        rel_config,
                        f"Field group '{title}' has an entry that is not a field object.",
                    )
                    continue
                if is_module_field_group(child):
                    _issue(
                        issues,
                        "error",
                        rel_config,
                        f"Field group '{title}' cannot contain another group.",
                    )
                    continue
                if child.get("group") is not None:
                    _issue(
                        issues,
                        "error",
                        rel_config,
                        f"Field group '{title}' contains a field with 'group'. Nest fields instead.",
                    )
                _validate_one_module_field(child, rel_config, field_names, issues)
            continue
        if item.get("group") is not None:
            _issue(
                issues,
                "error",
                rel_config,
                "Do not set 'group' on a field. Use { group: \"Style\", fields: [...] }.",
            )
        _validate_one_module_field(item, rel_config, field_names, issues)

    for item in module.field_entries:
        for condition in item.get("visibleWhen") or []:
            if not isinstance(condition, dict):
                continue
            target = str(condition.get("field") or "").strip()
            operator = str(condition.get("operator") or "").strip().upper()
            name = str(item.get("name") or "?")

            if target and target not in field_names:
                _issue(
                    issues,
                    "error",
                    rel_config,
                    f"field '{name}' has a visibleWhen on unknown field '{target}'.",
                )
            if operator and operator not in CONDITION_OPERATORS:
                _issue(
                    issues,
                    "error",
                    rel_config,
                    f"field '{name}' has unknown visibleWhen operator '{operator}'.",
                )
            if operator in LIST_CONDITION_OPERATORS and not isinstance(
                condition.get("value"), list
            ):
                _issue(
                    issues,
                    "error",
                    rel_config,
                    f"field '{name}' uses {operator}, which needs a list 'value'.",
                )

        if str(item.get("type") or "").strip().upper() != "REPEATABLE":
            continue
        nested = item.get("itemFields")
        if not isinstance(nested, list):
            continue
        nested_names = set(field_names)
        for child in nested:
            if isinstance(child, dict):
                child_name = str(child.get("name") or "").strip()
                if child_name:
                    nested_names.add(child_name)
        parent_name = str(item.get("name") or "?")
        for child in nested:
            if not isinstance(child, dict):
                continue
            child_name = str(child.get("name") or "").strip() or "?"
            for condition in child.get("visibleWhen") or []:
                if not isinstance(condition, dict):
                    continue
                target = str(condition.get("field") or "").strip()
                operator = str(condition.get("operator") or "").strip().upper()
                scoped = f"{parent_name}.{child_name}"
                if target and target not in nested_names:
                    _issue(
                        issues,
                        "error",
                        rel_config,
                        f"field '{scoped}' has a visibleWhen on unknown field '{target}'.",
                    )
                if operator and operator not in CONDITION_OPERATORS:
                    _issue(
                        issues,
                        "error",
                        rel_config,
                        f"field '{scoped}' has unknown visibleWhen operator '{operator}'.",
                    )
                if operator in LIST_CONDITION_OPERATORS and not isinstance(
                    condition.get("value"), list
                ):
                    _issue(
                        issues,
                        "error",
                        rel_config,
                        f"field '{scoped}' uses {operator}, which needs a list 'value'.",
                    )


def _validate_one_module_field(
    item: dict,
    rel_config: str,
    field_names: set[str],
    issues: list[ValidationIssue],
) -> None:
    name = str(item.get("name") or "").strip()
    if not name:
        _issue(issues, "error", rel_config, "A field is missing 'name'.")
        return
    if not SETTING_FIELD_NAME_RE.match(name):
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' must be snake_case (a-z, 0-9, underscore).",
        )
    if name in field_names:
        _issue(issues, "error", rel_config, f"Duplicate field '{name}'.")
    field_names.add(name)

    if not str(item.get("label") or "").strip():
        _issue(issues, "error", rel_config, f"field '{name}' is missing 'label'.")

    field_type = str(item.get("type") or "").strip()
    if not field_type:
        _issue(issues, "error", rel_config, f"field '{name}' is missing 'type'.")
    elif field_type in DISALLOWED_MODULE_FIELD_TYPES:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' uses {field_type}, which is not available on modules. "
            "A page document is public, so it must not hold a secret, and an "
            "ACTION button belongs on a settings screen.",
        )
    elif field_type not in MODULE_FIELD_TYPES:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' has unknown type '{field_type}'.",
        )
    elif field_type in SELECT_FIELD_TYPES and not item.get("options"):
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' is {field_type} and needs 'options'. "
            "Modules cannot use a serverless optionsSource; the builder renders "
            "field inputs without invoking the app runtime.",
        )

    if item.get("optionsSource"):
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' declares optionsSource, which modules do not support. "
            "Use static 'options' instead.",
        )

    if field_type == "REPEATABLE":
        _validate_repeatable_field(item, name, rel_config, issues)

    _validate_filter_traits(item, f"{rel_config}:{name}", issues)
    _validate_property_filters(item, f"{rel_config}:{name}", issues)


def _validate_repeatable_field(
    item: dict,
    name: str,
    rel_config: str,
    issues: list[ValidationIssue],
) -> None:
    """A REPEATABLE field is a list of tiles; authors set min/max and itemFields."""
    nested = item.get("itemFields")
    if not isinstance(nested, list) or not nested:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' is REPEATABLE and needs 'itemFields' — the schema "
            "for one item. Set 'min' and 'max' so editors can add items without "
            "a count dropdown.",
        )
        return

    minimum = item.get("min", 0)
    maximum = item.get("max", 20)
    if not isinstance(minimum, int) or minimum < 0:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' min must be an integer of 0 or more.",
        )
        minimum = 0
    if not isinstance(maximum, int) or maximum < 1:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' max must be an integer of 1 or more.",
        )
        maximum = 20
    if maximum > 50:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' max cannot be more than 50.",
        )
    if maximum < minimum:
        _issue(
            issues,
            "error",
            rel_config,
            f"field '{name}' max ({maximum}) is less than min ({minimum}).",
        )

    child_names: set[str] = set()
    for child in nested:
        if not isinstance(child, dict):
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}' has an itemFields entry that is not a field object.",
            )
            continue
        child_name = str(child.get("name") or "").strip()
        if not child_name:
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}' has an itemFields entry missing 'name'.",
            )
            continue
        if not SETTING_FIELD_NAME_RE.match(child_name):
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' must be snake_case (a-z, 0-9, underscore).",
            )
        if child_name in child_names:
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}' has duplicate itemFields name '{child_name}'.",
            )
        child_names.add(child_name)
        if not str(child.get("label") or "").strip():
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' is missing 'label'.",
            )
        child_type = str(child.get("type") or "").strip()
        if not child_type:
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' is missing 'type'.",
            )
        elif child_type == "REPEATABLE":
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' cannot be REPEATABLE. Nesting lists "
                "is not supported; keep one itemFields level.",
            )
        elif child_type in DISALLOWED_MODULE_FIELD_TYPES:
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' uses {child_type}, which is not "
                "available on modules.",
            )
        elif child_type not in MODULE_FIELD_TYPES:
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' has unknown type '{child_type}'.",
            )
        elif child_type in SELECT_FIELD_TYPES and not child.get("options"):
            _issue(
                issues,
                "error",
                rel_config,
                f"field '{name}.{child_name}' is {child_type} and needs 'options'.",
            )


def _validate_module_frameworks(
    module: Any,
    rel_dir: str,
    rel_config: str,
    issues: list[ValidationIssue],
) -> None:
    declared = module.frameworks

    for framework, range_spec in declared.items():
        if framework not in PINNED_FRAMEWORK_MAJORS:
            _issue(
                issues,
                "error",
                rel_config,
                f"Unknown framework '{framework}'. "
                f"Supported: {sorted(PINNED_FRAMEWORK_MAJORS)}.",
            )
            continue

        major = parse_major(range_spec)
        pinned = PINNED_FRAMEWORK_MAJORS[framework]
        if major is None:
            _issue(
                issues,
                "warning",
                rel_config,
                f"Could not read a major version from {framework} range '{range_spec}'.",
            )
        elif major != pinned:
            _issue(
                issues,
                "error",
                rel_config,
                f"{framework} range '{range_spec}' targets major {major}, but the "
                f"platform pins {pinned}. A build hoists one copy of each framework, "
                "so a mismatch would break every site that installs this app "
                "alongside another.",
            )

        if not module.island_files(framework):
            _issue(
                issues,
                "warning",
                rel_dir,
                f"Declares {framework} but has no {framework}/ island files.",
            )

    # A JSX island outside its framework folder is invisible to Astro's
    # include patterns, so it would be compiled by the wrong renderer or none.
    for path in module.directory.rglob("*"):
        if path.suffix not in {".jsx", ".tsx"}:
            continue
        relative = path.relative_to(module.directory)
        top = relative.parts[0] if len(relative.parts) > 1 else ""
        if top not in JSX_FRAMEWORKS:
            _issue(
                issues,
                "error",
                f"{rel_dir}/{relative}",
                "JSX island must live in a framework folder "
                f"({', '.join(f'{f}/' for f in JSX_FRAMEWORKS)}). React, Preact and "
                "Solid share the .jsx/.tsx extensions, so Astro can only tell them "
                "apart by path.",
            )
        elif top not in declared:
            _issue(
                issues,
                "error",
                rel_config,
                f"Module ships {top}/ islands but does not declare '{top}' under "
                "'frameworks'.",
            )


def _validate_against_json_schemas(
    root: Path,
    config: ProjectConfig,
    issues: list[ValidationIssue],
) -> None:
    """Optional structural checks via jsonschema when the extra is installed."""
    try:
        import jsonschema
    except ImportError:
        return

    from caraer_cli.project.json_schemas import SCHEMA_FILENAMES, schemas_dir
    from caraer_cli.project.paths import lifecycle_dir

    schema_root = schemas_dir()
    if schema_root is None:
        return

    import json

    cache: dict[str, Any] = {}

    def load_schema(kind: str) -> Any | None:
        if kind in cache:
            return cache[kind]
        filename = SCHEMA_FILENAMES.get(kind)
        if not filename:
            return None
        path = schema_root / filename
        if not path.is_file():
            return None
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        cache[kind] = schema
        return schema

    def check(kind: str, rel: str, data: Any) -> None:
        schema = load_schema(kind)
        if schema is None or not isinstance(data, dict):
            return
        payload = {k: v for k, v in data.items() if k != "$schema"}
        try:
            jsonschema.validate(instance=payload, schema=schema)
        except jsonschema.ValidationError as exc:
            path_bits = ".".join(str(p) for p in exc.absolute_path) if exc.absolute_path else ""
            loc = f"{rel}:{path_bits}" if path_bits else rel
            _issue(
                issues,
                "warning",
                loc,
                f"JSON Schema: {exc.message}",
            )
        except Exception as exc:  # noqa: BLE001
            _issue(issues, "warning", rel, f"JSON Schema check failed: {exc}")

    try:
        if not config.privateApp:
            manifest = load_local_app(app_manifest_path(root, config.srcDir))
            check("app", str(app_manifest_path(root, config.srcDir).relative_to(root)), manifest)
    except Exception:  # noqa: BLE001
        pass

    for manifest, _entry, _code, _sources in discover_local_functions(root, config):
        fn_path = functions_dir(root, config.srcDir) / manifest.name / "function.caraer.json"
        if fn_path.is_file():
            try:
                data = json.loads(fn_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            check("function", str(fn_path.relative_to(root)), data)

    for path, item in discover_local_webhooks(root, config):
        check("webhook", str(path.relative_to(root)), item)
    for path, item in discover_local_schedules(root, config):
        check("schedule", str(path.relative_to(root)), item)
    for path, item in discover_local_inbound(root, config):
        check("inbound", str(path.relative_to(root)), item)

    hooks = discover_local_lifecycle(root, config)
    base = lifecycle_dir(root, config.srcDir)
    for stem, (manifest_key, _topic) in LIFECYCLE_HOOKS.items():
        hook = hooks.get(manifest_key)
        if hook is None:
            continue
        check("lifecycle", str((base / f"{stem}.json").relative_to(root)), hook)



def _validate_lifecycle(
    root: Path,
    config: ProjectConfig,
    function_names: set[str],
    issues: list[ValidationIssue],
) -> int:
    from caraer_cli.project.paths import lifecycle_dir

    hooks = discover_local_lifecycle(root, config)
    base = lifecycle_dir(root, config.srcDir)
    count = 0
    for stem, (manifest_key, expected_topic) in LIFECYCLE_HOOKS.items():
        hook = hooks.get(manifest_key)
        if hook is None:
            continue
        count += 1
        rel = str((base / f"{stem}.json").relative_to(root))
        topic = str(hook.get("topic") or "").strip()
        if topic and topic != expected_topic:
            _issue(
                issues,
                "error",
                f"{rel}:topic",
                f"topic must be '{expected_topic}' for {stem}.json.",
            )
        mode = str(hook.get("deliveryMode") or "SERVERLESS").strip().upper()
        if mode not in {"SERVERLESS", "HTTP"}:
            _issue(
                issues,
                "error",
                f"{rel}:deliveryMode",
                "deliveryMode must be SERVERLESS or HTTP.",
            )
        elif mode == "SERVERLESS":
            sf = hook.get("serverlessFunction")
            if not isinstance(sf, dict) or not (
                sf.get("name") or sf.get("uuid")
            ):
                _issue(
                    issues,
                    "error",
                    f"{rel}:serverlessFunction",
                    "SERVERLESS lifecycle hooks require serverlessFunction.name.",
                )
            else:
                _validate_sf_ref(sf, function_names, issues, rel)
        elif mode == "HTTP":
            url = str(hook.get("url") or "").strip()
            if not url:
                _issue(issues, "error", f"{rel}:url", "HTTP hooks require url.")
            elif not _looks_like_url(url):
                _issue(issues, "error", f"{rel}:url", "url must be an http(s) URL.")
    return count
