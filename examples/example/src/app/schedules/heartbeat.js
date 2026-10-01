// req.body.action is "app.schedule". The schedule is req.body.payload
// ({ scheduleName, ...template }). Token and settingsSchema are on req.body.
import { contextFrom, putState, ok } from "../shared/index.js";

export const handler = async (req, res) => {
  const ctx = contextFrom(req);
  const ranAt = new Date().toISOString();
  if (ctx.token && ctx.appUuid) {
    await putState(ctx, { lastHeartbeatAt: ranAt });
  }
  ok(res, {
    functionName: "heartbeat",
    displayName: ctx.settings.display_name,
    ranAt,
  });
};

export const manifest = {
  schedule: "0 0 */12 * * *",
  enabled: true,
  description: "Writes lastHeartbeatAt to installation state every 12 hours.",
};
