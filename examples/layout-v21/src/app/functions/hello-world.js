const { contextFrom, objectNameFromSetting, ok } = require("../shared");

exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  ok(res, {
    functionName: ctx.functionName || "hello-world",
    topic: ctx.topic,
    displayName: ctx.settings.display_name,
    targetObject: objectNameFromSetting(ctx.settings.target_object),
    companyUuid: ctx.companyUuid,
  });
};

exports.manifest = {
  description: "Runs when a record is created on the installer-chosen object.",
  webhooks: [{ topic: "record.<setting:target_object>.created" }],
};
