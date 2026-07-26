const {
  parseBody,
  flattenSettings,
  apiBaseFrom,
  maxEventsFrom,
  inboxLabelFrom,
  inboundPayload,
  getState,
  putState,
} = require("./shared");

/**
 * Inbound catcher — stores the latest webhook payloads in installation state.
 */
exports.handler = async (req, res) => {
  try {
    const body = parseBody(req);
    const settings = flattenSettings(body.settingsSchema);
    const apiBase = apiBaseFrom(body);
    const token = body.installationToken;
    const appUuid = body.appUuid;
    const label = inboxLabelFrom(settings);
    const maxEvents = maxEventsFrom(settings);
    const payload = inboundPayload(body);
    const receivedAt = new Date().toISOString();

    const event = {
      receivedAt,
      inboxLabel: label,
      payload,
    };

    let events = [event];
    let totalCaught = 1;

    if (token && appUuid) {
      const state = await getState(apiBase, token, appUuid);
      const prior = Array.isArray(state.events) ? state.events : [];
      events = [event, ...prior].slice(0, maxEvents);
      totalCaught = Number(state.totalCaught || 0) + 1;
      await putState(apiBase, token, appUuid, {
        inboxLabel: label,
        maxEvents,
        totalCaught,
        lastReceivedAt: receivedAt,
        events,
      });
    }

    return res.status(200).json({
      ok: true,
      inboxLabel: label,
      stored: Boolean(token && appUuid),
      totalCaught,
      eventCount: events.length,
      latest: event,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
};
