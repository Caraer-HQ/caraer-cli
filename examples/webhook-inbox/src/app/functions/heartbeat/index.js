const {
  parseBody,
  flattenSettings,
  apiBaseFrom,
  inboxLabelFrom,
  getState,
  putState,
} = require("./shared");

/**
 * Schedule tick — records lastHeartbeatAt without appending inbox events.
 */
exports.handler = async (req, res) => {
  try {
    const body = parseBody(req);
    const settings = flattenSettings(body.settingsSchema);
    const apiBase = apiBaseFrom(body);
    const token = body.installationToken;
    const appUuid = body.appUuid;
    const label = inboxLabelFrom(settings);
    const at = new Date().toISOString();

    if (token && appUuid) {
      const state = await getState(apiBase, token, appUuid);
      await putState(apiBase, token, appUuid, {
        ...state,
        inboxLabel: label,
        lastHeartbeatAt: at,
      });
    }

    return res.status(200).json({ ok: true, inboxLabel: label, lastHeartbeatAt: at });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
};
