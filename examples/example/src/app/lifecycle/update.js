import { contextFrom, putState, ok } from "../shared/index.js";

export const handler = async (req, res) => {
  const ctx = contextFrom(req);
  const updatedAt = new Date().toISOString();
  if (ctx.token && ctx.appUuid) {
    await putState(ctx, {
      updatedAt,
      displayName: ctx.settings.display_name || null,
    });
  }
  ok(res, {
    functionName: "update",
    updatedAt,
  });
};

export const manifest = {
  lifecycle: "update",
  topic: "app.updated",
  label: "App updated",
  waitUntilComplete: true,
};
