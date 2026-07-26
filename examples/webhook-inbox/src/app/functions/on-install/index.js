const {
  parseBody,
  flattenSettings,
  apiBaseFrom,
  inboxLabelFrom,
  maxEventsFrom,
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
      await putState(apiBase, token, appUuid, {
        inboxLabel: label,
        maxEvents,
        events: [],
        totalCaught: 0,
        installedAt: new Date().toISOString(),
      });
    }

    return res.status(200).json({
      ok: true,
      event: body.event || "Installed",
      inboxLabel: label,
      nextSteps: [
        "Copy the inbound URL from the app install / inbound routes",
        "POST JSON to it with header X-Caraer-Inbound-Secret",
        "Use Clear inbox on a record preview to wipe stored events",
      ],
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
};
