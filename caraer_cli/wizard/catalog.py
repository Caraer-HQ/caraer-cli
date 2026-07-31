"""Static marketplace catalogs mirrored from the Caraer backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subcategory:
    key: str
    label: str


@dataclass(frozen=True)
class MainCategory:
    key: str
    label: str
    subcategories: tuple[Subcategory, ...]


def _slugify(label: str) -> str:
    normalized = label.strip().lower().replace("&", "and")
    chars: list[str] = []
    prev_underscore = False
    for ch in normalized:
        if ch.isalnum():
            chars.append(ch)
            prev_underscore = False
        elif not prev_underscore:
            chars.append("_")
            prev_underscore = True
    return "".join(chars).strip("_")


def _category(label: str, sub_labels: list[str]) -> MainCategory:
    return MainCategory(
        key=_slugify(label),
        label=label,
        subcategories=tuple(Subcategory(key=_slugify(s), label=s) for s in sub_labels),
    )


MAIN_CATEGORIES: tuple[MainCategory, ...] = (
    _category(
        "Productivity",
        ["Agenda", "Tasks", "Notes", "Documents", "Files", "Automation", "Forms"],
    ),
    _category(
        "Communication",
        [
            "Email",
            "Chat",
            "Meetings",
            "Calling",
            "Notifications",
            "Customer Conversations",
            "Social Messaging",
        ],
    ),
    _category(
        "Recruitment",
        [
            "ATS",
            "Job Posting",
            "Sourcing",
            "Candidate Communication",
            "Career Sites",
            "Screening",
            "Interview Scheduling",
            "Analytics",
        ],
    ),
    _category(
        "HR",
        ["HRIS", "Onboarding", "Payroll", "Contracts", "Learning", "Engagement", "Compliance"],
    ),
    _category(
        "Marketing",
        [
            "Email Marketing",
            "Social Media",
            "Campaigns",
            "Content",
            "SEO",
            "Advertising",
            "Automation",
            "Branding",
        ],
    ),
    _category(
        "Sales",
        [
            "CRM",
            "Lead Generation",
            "Enrichment",
            "Outreach",
            "Proposals",
            "Account Management",
            "Analytics",
        ],
    ),
    _category(
        "Data",
        [
            "Dashboards",
            "Reporting",
            "Spreadsheets",
            "Visualization",
            "Data Management",
            "Predictions",
        ],
    ),
    _category(
        "Finance",
        ["Invoicing", "Payments", "Bookkeeping", "Expenses", "Budgeting", "Reporting"],
    ),
    _category(
        "Customer Support",
        ["Helpdesk", "Ticketing", "Live Chat", "Knowledge Base", "Feedback", "Analytics"],
    ),
    _category(
        "Developer Tools",
        [
            "Code",
            "Repositories",
            "APIs",
            "Webhooks",
            "DevOps",
            "Monitoring",
            "Testing",
            "No-code",
        ],
    ),
    _category(
        "Education & Learning",
        [
            "Courses",
            "Training",
            "Onboarding",
            "Coaching",
            "Assessments",
            "Knowledge Sharing",
        ],
    ),
)

APP_BAR_LOCATIONS: tuple[tuple[str, str], ...] = (
    ("RECORD_PREVIEW", "Record preview (action)"),
    ("RECORD_OVERVIEW", "Record overview (action)"),
    ("RECORD_DETAIL", "Record detail (iframe)"),
    ("TOOL_BAR", "Tool bar (iframe)"),
    ("TRAIT_BAR", "Trait bar (iframe)"),
)

ACTION_BASED_LOCATIONS = {"RECORD_PREVIEW", "RECORD_OVERVIEW"}

SETTING_FIELD_TYPES: tuple[tuple[str, str], ...] = (
    ("SINGLE_LINE", "Single line text"),
    ("MULTI_LINE", "Multi-line text"),
    ("SWITCH", "Switch / boolean"),
    ("SECRET", "Secret (write-only)"),
    ("SINGLE_SELECT", "Single select (static or dynamic options)"),
    ("MULTI_SELECT", "Multi select (static or dynamic options)"),
    ("OBJECT_SINGLE_SELECT", "Object select (single)"),
    ("OBJECT_MULTI_SELECT", "Object select (multi)"),
    ("PROPERTY_SINGLE_SELECT", "Property select (single)"),
    ("PROPERTY_MULTI_SELECT", "Property select (multi)"),
    ("RECORD_SINGLE_SELECT", "Record select (single, static options)"),
    ("RECORD_MULTI_SELECT", "Record select (multi, static options)"),
    ("MAPPING", "Property mapping"),
)

# Types that may load options via optionsSource.serverlessFunctionName.
DYNAMIC_OPTIONS_FIELD_TYPES = frozenset({"SINGLE_SELECT", "MULTI_SELECT"})

# Types that need a static options[] list (no platform object/property picker).
STATIC_OPTIONS_FIELD_TYPES = frozenset(
    {
        "SINGLE_SELECT",
        "MULTI_SELECT",
        "RECORD_SINGLE_SELECT",
        "RECORD_MULTI_SELECT",
    }
)

# Installer picks from the company schema — no creator-time options list.
SCHEMA_PICKER_FIELD_TYPES = frozenset(
    {
        "OBJECT_SINGLE_SELECT",
        "OBJECT_MULTI_SELECT",
        "PROPERTY_SINGLE_SELECT",
        "PROPERTY_MULTI_SELECT",
    }
)


def find_main_category(key: str) -> MainCategory | None:
    for category in MAIN_CATEGORIES:
        if category.key == key:
            return category
    return None
