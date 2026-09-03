"""Public-app scope macro catalog (mirrors the Caraer creator / backend)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeMacroPreset:
    """A supported creator-side scope macro pattern."""

    id: str
    title: str
    pattern: str
    example: str
    description: str
    when_to_use: str
    needs_tool: bool = False
    needs_object: bool = False
    needs_setting_field: bool = False
    needs_trait: bool = False


SCOPE_MACRO_PRESETS: tuple[ScopeMacroPreset, ...] = (
    ScopeMacroPreset(
        id="global.all",
        title="All global scopes",
        pattern="global.all",
        example="global.all",
        description="Expands to every scope that starts with `global.`.",
        when_to_use=(
            "Use when your app needs platform-wide capabilities "
            "(not tied to a specific record)."
        ),
    ),
    ScopeMacroPreset(
        id="tools.tool.all",
        title="All scopes for a tool",
        pattern="tools.<tool>.all",
        example="tools.forms.all",
        description=(
            "Expands to every scope that starts with `tools.<tool>.` "
            "(for the concrete tool name you put in the macro)."
        ),
        when_to_use=(
            "Use when your app only touches one tool area, but needs the "
            "full set of that tool's scopes."
        ),
        needs_tool=True,
    ),
    ScopeMacroPreset(
        id="records.object.all",
        title="Record-level scopes for one object",
        pattern="records.<object>.all",
        example="records.candidate.all",
        description=(
            "Expands to record-level scopes for `<object>`, excluding "
            "`.property.` and `.relation.` scopes."
        ),
        when_to_use=(
            "Use when your app reads/writes a record, but does not need to "
            "manage specific properties or relations."
        ),
        needs_object=True,
    ),
    ScopeMacroPreset(
        id="records.*.all",
        title="Record-level scopes for all objects",
        pattern="records.*.all",
        example="records.*.all",
        description=(
            "Expands to every record-level scope in the tenant catalog "
            "(excludes `.property.` and `.relation.`)."
        ),
        when_to_use=(
            "Use with care. It usually grants broad access across many "
            "record types."
        ),
    ),
    ScopeMacroPreset(
        id="records.object.properties_all",
        title="Property scopes for one object",
        pattern="records.<object>.properties_all",
        example="records.candidate.properties_all",
        description="Expands to all `.property.` scopes for `<object>`.",
        when_to_use=(
            "Use when your app needs to manage or validate specific fields "
            "on a record."
        ),
        needs_object=True,
    ),
    ScopeMacroPreset(
        id="records.*.properties_all",
        title="Property scopes for all objects",
        pattern="records.*.properties_all",
        example="records.*.properties_all",
        description="Expands to all `.property.` scopes for every record object.",
        when_to_use=(
            "Use with care if you only need a subset of properties; prefer "
            "the `<object>` variant."
        ),
    ),
    ScopeMacroPreset(
        id="records.object.relations_all",
        title="Relation scopes for one object",
        pattern="records.<object>.relations_all",
        example="records.candidate.relations_all",
        description="Expands to all `.relation.` scopes for `<object>`.",
        when_to_use=(
            "Use when your app works with relations between records "
            "(e.g. linked entities)."
        ),
        needs_object=True,
    ),
    ScopeMacroPreset(
        id="records.*.relations_all",
        title="Relation scopes for all objects",
        pattern="records.*.relations_all",
        example="records.*.relations_all",
        description="Expands to all `.relation.` scopes for every record object.",
        when_to_use=(
            "Use with care; relation access can be broad and may unlock "
            "many actions."
        ),
    ),
    ScopeMacroPreset(
        id="records.object.pack",
        title="Full pack for one object (all + properties + relations)",
        pattern="records.<object>.{all,properties_all,relations_all}",
        example="records.candidate.all + properties_all + relations_all",
        description=(
            "Adds the three common macros for one object in one step: "
            "`records.<object>.all`, `.properties_all`, and `.relations_all`."
        ),
        when_to_use=(
            "Recommended when your app fully works with one record type."
        ),
        needs_object=True,
    ),
    ScopeMacroPreset(
        id="records.setting.all",
        title="Record-level scopes from a setting",
        pattern="records.<setting:{field}>.all",
        example="records.<setting:attendee_object>.all",
        description=(
            "Same as `records.<object>.all`, but the object name comes from "
            "an installer setting. Bare `<field>` is still supported; prefer "
            "`<setting:field>` in new apps."
        ),
        when_to_use=(
            "Use when the target object is chosen at install time "
            "(OBJECT_* or MAPPING)."
        ),
        needs_setting_field=True,
    ),
    ScopeMacroPreset(
        id="records.setting.properties_all",
        title="Property scopes from a setting",
        pattern="records.<setting:{field}>.properties_all",
        example="records.<setting:attendee_object>.properties_all",
        description=(
            "Expands to all `.property.` scopes for the object selected in "
            "`{field}`."
        ),
        when_to_use="Use with a mapping or object-select setting.",
        needs_setting_field=True,
    ),
    ScopeMacroPreset(
        id="records.setting.relations_all",
        title="Relation scopes from a setting",
        pattern="records.<setting:{field}>.relations_all",
        example="records.<setting:attendee_object>.relations_all",
        description=(
            "Expands to all `.relation.` scopes for the object selected in "
            "`{field}`."
        ),
        when_to_use="Use when the app writes relations on the selected object.",
        needs_setting_field=True,
    ),
    ScopeMacroPreset(
        id="records.setting.pack",
        title="Full pack from a setting (all + properties + relations)",
        pattern="records.<setting:{field}>.{all,properties_all,relations_all}",
        example=(
            "records.<setting:attendee_object>.all + properties_all + "
            "relations_all"
        ),
        description=(
            "Adds the three common macros for the object stored in a setting. "
            "Bare `<field>` still works."
        ),
        when_to_use="Recommended when the app fully works with a selected object.",
        needs_setting_field=True,
    ),
    ScopeMacroPreset(
        id="records.trait.all",
        title="Record-level scopes for every object with a trait",
        pattern="records.<trait:{trait}>.all",
        example="records.<trait:user>.all",
        description=(
            "Expands to record-level scopes for each object that has that "
            "trait (e.g. `user` → employee, partner_user)."
        ),
        when_to_use=(
            "Use when the app must reach every object that implements a "
            "trait, not a single setting-selected object."
        ),
        needs_trait=True,
    ),
    ScopeMacroPreset(
        id="records.trait.properties_all",
        title="Property scopes for every object with a trait",
        pattern="records.<trait:{trait}>.properties_all",
        example="records.<trait:user>.properties_all",
        description=(
            "Expands to all `.property.` scopes for objects marked with "
            "`{trait}`."
        ),
        when_to_use="Use when the app reads or writes fields on trait objects.",
        needs_trait=True,
    ),
    ScopeMacroPreset(
        id="records.trait.pack",
        title="Record + property pack for every object with a trait",
        pattern="records.<trait:{trait}>.{all,properties_all}",
        example="records.<trait:user>.all + properties_all",
        description=(
            "Adds `.all` and `.properties_all` for every object with that "
            "trait. Add `.relations_all` only if the app writes those links."
        ),
        when_to_use="Use when the app works with all objects of a trait.",
        needs_trait=True,
    ),
)

KNOWN_TOOL_NAMES: tuple[str, ...] = (
    "apps",
    "automations",
    "inbox",
    "company_settings",
    "environments",
    "forms",
    "files",
    "modules",
    "objects_schemas",
    "users",
    "views",
    "web_menus",
    "previews",
    "sync",
    "feeds",
    "analytics",
)

COMMON_OBJECT_NAMES: tuple[str, ...] = (
    "candidate",
    "contact",
    "vacancy",
    "application",
    "company",
    "person",
)

COMMON_TRAIT_NAMES: tuple[str, ...] = (
    "user",
    "event",
    "task",
    "message",
    "action",
    "page",
    "flow",
    "table",
    "analytics",
)

EXACT_SCOPE_EXAMPLES: tuple[str, ...] = (
    "tools.apps.read",
    "tools.apps.write",
    "tools.forms.read",
    "tools.forms.write",
    "tools.objects_schemas.read",
    "tools.objects_schemas.write",
    "tools.files.read",
    "tools.files.write",
    "tools.automations.read",
    "tools.automations.write",
    "tools.inbox.read",
    "tools.inbox.write",
)


def find_preset(preset_id: str) -> ScopeMacroPreset | None:
    for preset in SCOPE_MACRO_PRESETS:
        if preset.id == preset_id:
            return preset
    return None


def materialize_macro(
    preset: ScopeMacroPreset,
    *,
    tool: str | None = None,
    object_name: str | None = None,
    setting_field: str | None = None,
    trait_name: str | None = None,
) -> list[str]:
    """Turn a macro preset into one or more concrete requiredScopes strings."""
    if preset.id == "records.object.pack":
        if not object_name:
            raise ValueError("object_name is required for this macro")
        obj = object_name.strip()
        return [
            f"records.{obj}.all",
            f"records.{obj}.properties_all",
            f"records.{obj}.relations_all",
        ]
    if preset.id == "records.setting.pack":
        if not setting_field:
            raise ValueError("setting_field is required for this macro")
        field = setting_field.strip()
        return [
            f"records.<setting:{field}>.all",
            f"records.<setting:{field}>.properties_all",
            f"records.<setting:{field}>.relations_all",
        ]
    if preset.id == "records.trait.pack":
        if not trait_name:
            raise ValueError("trait_name is required for this macro")
        trait = trait_name.strip()
        return [
            f"records.<trait:{trait}>.all",
            f"records.<trait:{trait}>.properties_all",
        ]

    pattern = preset.pattern
    if preset.needs_tool:
        if not tool:
            raise ValueError("tool is required for this macro")
        pattern = pattern.replace("<tool>", tool.strip())
    if preset.needs_object:
        if not object_name:
            raise ValueError("object_name is required for this macro")
        pattern = pattern.replace("<object>", object_name.strip())
    if preset.needs_setting_field:
        if not setting_field:
            raise ValueError("setting_field is required for this macro")
        pattern = pattern.replace("{field}", setting_field.strip())
    if preset.needs_trait:
        if not trait_name:
            raise ValueError("trait_name is required for this macro")
        pattern = pattern.replace("{trait}", trait_name.strip())
    return [pattern]
