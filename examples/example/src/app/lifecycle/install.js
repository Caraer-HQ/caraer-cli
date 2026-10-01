// req.body.event is "Installed" | "Updated" | "Uninstalled" | "Rotated".
// installationToken, caraerApiBase, and settingsSchema sit on req.body.
import { contextFrom, putState, runSql, ok } from "../shared/index.js";

export const handler = async (req, res) => {
  const ctx = contextFrom(req);
  const installedAt = new Date().toISOString();
  let state = null;
  let db = null;
  if (ctx.token && ctx.appUuid) {
    state = await putState(ctx, {
      installedAt,
      displayName: ctx.settings.display_name || "Example",
    });
    db = await runSql(ctx, [
      {
        sql:
          "CREATE TABLE IF NOT EXISTS notes (" +
          "id serial PRIMARY KEY, body text, created_at timestamptz" +
          " DEFAULT now())",
        params: [],
      },
      {
        sql: "INSERT INTO notes (body) VALUES ($1)",
        params: [`installed ${installedAt}`],
      },
    ]);
  }
  ok(res, {
    functionName: "install",
    installedAt,
    stateStatus: state && state.status,
    dbStatus: db && db.status,
    dbOk: Boolean(db && db.ok),
  });
};

export const manifest = {
  lifecycle: "install",
  topic: "app.installed",
  label: "App installed",
  waitUntilComplete: true,
};
