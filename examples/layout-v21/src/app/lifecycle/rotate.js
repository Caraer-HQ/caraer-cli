const { contextFrom, putState, ok } = require("../shared");

exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  const rotatedAt = new Date().toISOString();
  if (ctx.token && ctx.appUuid) {
    await putState(ctx, { rotatedAt });
  }
  ok(res, { functionName: "rotate", rotatedAt });
};

exports.manifest = {
  lifecycle: "rotate",
  topic: "app.rotated",
  label: "Credentials rotated",
};
