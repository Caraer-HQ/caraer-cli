const { contextFrom, putState, ok } = require("../shared");

exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  const receivedAt = new Date().toISOString();
  if (ctx.settings.log_events && ctx.token && ctx.appUuid) {
    await putState(ctx, {
      lastInboundAt: receivedAt,
      lastInboundFunction: "echo",
    });
  }
  ok(res, {
    functionName: "echo",
    displayName: ctx.settings.display_name,
    receivedAt,
    inboundBody: ctx.body.payload || ctx.body,
  });
};

exports.manifest = {
  authMode: "NONE",
  enqueue: false,
  enabled: true,
  description: "Public echo endpoint for layout testing.",
};
