const { contextFrom, objectNameFromSetting, ok } = require("../shared");

// req.body is the webhook.
//
// Record created (USER_FRIENDLY). The record is body.record.record.
// {
//   event: { type: "Created", timestamp, correlationId },
//   record: { record: { uuid, objectName, properties }, relations },
//   user: { type, uuid, email, firstname, lastname, companyUuid },
//   context: { companyUuid },
//   appUuid, companyUuid, caraerApiBase, installationToken,
//   settingsSchema: [{ name, type, value }],  // installation settings
//   scopes, secrets, connections
// }
//
// The overview dialog's Preview button calls this function. Dialog answers
// are flat on body.appBarSettingsValues. The app bars themselves live in
// src/app/appbars/ping.js.
exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  const record = ctx.record;
  ok(res, {
    functionName: ctx.functionName || "hello-world",
    eventType: ctx.eventType,
    recordUuid: record ? record.uuid : ctx.body.recordUuid || null,
    objectName: record ? record.objectName : ctx.body.object || null,
    properties: record ? record.properties : null,
    displayName: ctx.settings.display_name,
    targetObject: objectNameFromSetting(ctx.settings.target_object),
    companyUuid: ctx.companyUuid,
    appBarUuid: ctx.body.appBarUuid || null,
    dialog: ctx.dialog,
  });
};

exports.manifest = {
  description: "Runs when a record is created on the installer-chosen object.",
  webhooks: [{
    topic: "record.<setting:target_object>.created",
    label: "Record created",
  }],
};
