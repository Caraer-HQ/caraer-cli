// Direct inbound: req.body.body is the HTTP JSON, req.body.action is
// "app.inbound". Queued inbound wraps that object as req.body.payload.
import { contextFrom, putState, ok } from "../shared/index.js";

export const handler = async (req, res) => {
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

export const manifest = {
  authMode: "NONE",
  enqueue: false,
  enabled: true,
  description: "Public echo endpoint for layout testing.",
};
