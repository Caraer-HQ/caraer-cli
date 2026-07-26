const {
  parseBody,
  flattenSettings,
  apiBaseFrom,
  inboxLabelFrom,
  maxEventsFrom,
  getState,
  putState,
} = require("./shared");

exports.handler = async (req, res) => {
  try {
    const body = parseBody(req);
    const settings = flattenSettings(body.settingsSchema);
    const apiBase = apiBaseFrom(body);
    const token = body.installationToken;
    const appUuid = body.appUuid;
    const label = inboxLabelFrom(settings);
    const maxEvents = maxEventsFrom(settings);

    if (token && appUuid) {
      const state = await getState(apiBase, token, appUuid);
      const events = Array.isArray(state.events)
        ? state.events.slice(0, maxEvents)
        : [];
      await putState(apiBase, token, appUuid, {
        ...state,
        inboxLabel: label,
        maxEvents,
        events,
        updatedAt: new Date().toISOString(),
      });
    }

    return res.status(200).json({
      ok: true,
      event: body.event || "Updated",
      inboxLabel: label,
      maxEvents,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
};
