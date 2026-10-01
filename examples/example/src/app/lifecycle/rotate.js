import { contextFrom, putState, ok } from "../shared/index.js";

export const handler = async (req, res) => {
  const ctx = contextFrom(req);
  const rotatedAt = new Date().toISOString();
  if (ctx.token && ctx.appUuid) {
    await putState(ctx, { rotatedAt });
  }
  ok(res, { functionName: "rotate", rotatedAt });
};

export const manifest = {
  lifecycle: "rotate",
  topic: "app.rotated",
  label: "Credentials rotated",
};
