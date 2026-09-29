const { contextFrom, ok } = require("../shared");

// Action bars (RECORD_PREVIEW, RECORD_OVERVIEW, RECORD_TRAIT) open
// settingsSchema as a dialog. Submitted values arrive as
// body.appBarSettingsValues. Iframe bars (RECORD_DETAIL, TOOL_BAR,
// TRAIT_BAR) need iframeUrl and do not call this function.
exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  ok(res, {
    functionName: ctx.functionName || "ping",
    eventType: ctx.eventType,
    recordUuid: ctx.body.recordUuid || null,
    objectName: ctx.body.object || null,
    dialog: ctx.dialog,
  });
};

exports.manifest = {
  description: "Action and iframe app bars.",
  appBars: [
    {
      name: "ping_overview",
      location: "RECORD_OVERVIEW",
      label: "Layout v21 ping",
      actionLabel: "Run",
      tooltipLabel: "Collect dialog fields, then run ping",
      description: "Every app-bar dialog field type on a record overview action.",
      icon: "bolt",
      settingsSchema: [
        {
          name: "note",
          label: "Note",
          type: "SINGLE_LINE",
          required: true,
          helpText: "One line of text.",
          defaultValue: "Hello",
        },
        {
          name: "details",
          label: "Details",
          type: "MULTI_LINE",
          helpText: "Several lines of text.",
        },
        {
          name: "notify_owner",
          label: "Notify the owner",
          type: "SWITCH",
          defaultValue: true,
          helpText: "Boolean. visibleWhen compares true and \"true\".",
        },
        {
          name: "priority",
          label: "Priority",
          type: "SINGLE_SELECT",
          required: true,
          helpText: "Static options. Each option is { name, label, helpText?, preview? }.",
          options: [
            { name: "low", label: "Low" },
            { name: "normal", label: "Normal", helpText: "Default handling" },
            { name: "high", label: "High", preview: "!" },
          ],
        },
        {
          name: "tags",
          label: "Tags",
          type: "MULTI_SELECT",
          helpText: "Static multi select. The value is a list of option names.",
          options: [
            { name: "urgent", label: "Urgent" },
            { name: "follow_up", label: "Follow up" },
          ],
        },
        {
          name: "channel",
          label: "Channel",
          type: "SINGLE_SELECT",
          helpText: "Dynamic options. Reloads when priority changes.",
          optionsSource: {
            type: "SERVERLESS",
            serverlessFunctionName: "list-dialog-options",
            dependsOn: ["priority"],
            searchable: true,
            minQueryLength: 0,
          },
        },
        {
          name: "linked_record",
          label: "Linked record",
          type: "RECORD_SINGLE_SELECT",
          helpText: "Record picker backed by a static options list.",
          options: [{ name: "current", label: "Current record" }],
        },
        {
          name: "extra_records",
          label: "Extra records",
          type: "RECORD_MULTI_SELECT",
          options: [
            { name: "current", label: "Current record" },
            { name: "related", label: "Related record" },
          ],
        },
        {
          name: "target_object",
          label: "Object",
          type: "OBJECT_SINGLE_SELECT",
          helpText: "Company objects. filterTraits keeps objects that have every listed trait.",
          filterTraits: ["user"],
        },
        {
          name: "related_objects",
          label: "Related objects",
          type: "OBJECT_MULTI_SELECT",
        },
        {
          name: "status_property",
          label: "Status property",
          type: "PROPERTY_SINGLE_SELECT",
        },
        {
          name: "copied_properties",
          label: "Properties to copy",
          type: "PROPERTY_MULTI_SELECT",
        },
        {
          name: "field_map",
          label: "Field map",
          type: "MAPPING",
          helpText: "Map source properties onto a target object.",
        },
        {
          name: "cv_file",
          label: "CV",
          type: "FILE",
          helpText: "One upload. The value is a file key.",
        },
        {
          name: "attachments",
          label: "Attachments",
          type: "MULTI_FILE",
          helpText: "Several uploads. The value is a list of file keys.",
        },
        {
          name: "photo",
          label: "Photo",
          type: "IMAGE",
          helpText: "Image upload with a thumbnail.",
        },
        {
          name: "accent",
          label: "Accent",
          type: "COLOR",
          defaultValue: "#3366FF",
          helpText: "Hex, rgba(), or a var(--caraer-color-*) token.",
        },
        {
          name: "api_token",
          label: "API token",
          type: "SECRET",
          helpText: "Write-only. A later read exposes hasValue, not the plaintext.",
        },
        {
          name: "show_advanced",
          label: "Show advanced fields",
          type: "SWITCH",
          defaultValue: false,
        },
        {
          name: "internal_code",
          label: "Internal code",
          type: "SINGLE_LINE",
          advanced: true,
          helpText: "Collapsed until Advanced is opened. Still stored.",
          visibleWhen: [
            { field: "show_advanced", operator: "EQUALS", value: true },
          ],
        },
        {
          name: "skip_when_high",
          label: "Skip when high",
          type: "SINGLE_LINE",
          visibleWhen: [
            { field: "priority", operator: "NOT_EQUALS", value: "high" },
            { field: "note", operator: "IS_SET" },
          ],
        },
        {
          name: "allowed_priorities",
          label: "Only for low or normal",
          type: "SINGLE_LINE",
          visibleWhen: [
            { field: "priority", operator: "IN", value: ["low", "normal"] },
          ],
        },
        {
          name: "blocked_priorities",
          label: "Hidden for low",
          type: "SINGLE_LINE",
          visibleWhen: [
            { field: "priority", operator: "NOT_IN", value: ["low"] },
          ],
        },
        {
          name: "when_empty",
          label: "When note is empty",
          type: "SINGLE_LINE",
          visibleWhen: [{ field: "note", operator: "IS_NOT_SET" }],
        },
        {
          name: "hidden_flag",
          label: "Hidden flag",
          type: "SINGLE_LINE",
          hidden: true,
          defaultValue: "kept-off-screen",
          helpText: "Not shown. Hidden fields are not required.",
        },
        {
          name: "steps",
          label: "Steps",
          type: "REPEATABLE",
          min: 0,
          max: 5,
          itemLabel: "Step",
          helpText: "A list of objects. itemFields is the schema of one item.",
          itemFields: [
            {
              name: "title",
              label: "Title",
              type: "SINGLE_LINE",
              required: true,
            },
            {
              name: "done",
              label: "Done",
              type: "SWITCH",
              defaultValue: false,
            },
          ],
        },
        {
          name: "preview_action",
          label: "Preview",
          type: "ACTION",
          helpText: "Button. Not stored, and it cannot be required.",
          actionSource: {
            type: "SERVERLESS",
            serverlessFunctionName: "hello-world",
          },
        },
      ],
    },
    {
      name: "ping_preview",
      location: "RECORD_PREVIEW",
      label: "Ping preview",
      actionLabel: "Ping",
      tooltipLabel: "Runs ping from the record preview",
      description: "Action bar on the record preview.",
      icon: "eye",
      settingsSchema: [
        {
          name: "reason",
          label: "Reason",
          type: "SINGLE_LINE",
          required: true,
        },
      ],
    },
    {
      name: "ping_trait",
      location: "RECORD_TRAIT",
      label: "Ping trait",
      actionLabel: "Ping",
      tooltipLabel: "Runs ping from a trait bar",
      description: "Action bar on objects that carry the trait.",
      icon: "user",
    },
    {
      name: "record_detail",
      location: "RECORD_DETAIL",
      label: "Record detail",
      tooltipLabel: "Embedded page on the record",
      description: "Iframe bar. No webhook and no dialog.",
      icon: "windowMaximize",
      iframeUrl: "https://example.com/caraer/record-detail",
    },
    {
      name: "tool_panel",
      location: "TOOL_BAR",
      label: "Tool panel",
      tooltipLabel: "Embedded tool",
      description: "Iframe in the tool bar.",
      icon: "wrench",
      iframeUrl: "https://example.com/caraer/tool",
    },
    {
      name: "trait_panel",
      location: "TRAIT_BAR",
      label: "Trait panel",
      tooltipLabel: "Embedded trait tool",
      description: "Iframe in the trait bar.",
      icon: "tags",
      iframeUrl: "https://example.com/caraer/trait",
    },
  ],
};
