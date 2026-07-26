const {
  parseBody,
  flattenSettings,
  apiBaseFrom,
  inboxLabelFrom,
  getState,
  putState,
} = require("./shared");

/**
 * App bar / manual clear — wipes stored events, keeps counters metadata.
 */
exports.handler = async (req, res) => {
  try {
    const body = parseBody(req);
    const settings = flattenSettings(body.settingsSchema);
    const apiBase = apiBaseFrom(body);
    const token = body.installationToken;
    const appUuid = body.appUuid;
    const label = inboxLabelFrom(settings);

    if (!token || !appUuid) {
      return res.status(200).json({
        ok: false,
        skipped: true,
        reason: "Missing installationToken or appUuid",
      });
    }

    const state = await getState(apiBase, token, appUuid);
    const cleared = Array.isArray(state.events) ? state.events.length : 0;
    await putState(apiBase, token, appUuid, {
      inboxLabel: label,
      events: [],
      lastClearedAt: new Date().toISOString(),
      lastClearedCount: cleared,
      totalCaught: Number(state.totalCaught || 0),
    });

    return res.status(200).json({
      ok: true,
      inboxLabel: label,
      cleared,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
};
