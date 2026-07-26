/**
 * Shared helpers for Webhook Inbox serverless functions.
 * Duplicated per function folder (each deploys independently).
 */

function parseBody(req) {
  if (!req || req.body == null) return {};
  if (typeof req.body === "string") {
    try {
      return JSON.parse(req.body || "{}");
    } catch (_) {
      return {};
    }
  }
  return req.body;
}

function flattenSettings(schema) {
  const out = {};
  if (!Array.isArray(schema)) return out;
  for (const field of schema) {
    if (field && field.name) {
      out[field.name] = field.value ?? field.defaultValue ?? null;
    }
  }
  return out;
}

function apiBaseFrom(body) {
  const raw =
    (body && body.caraerApiBase) ||
    process.env.CARAER_API_BASE ||
    process.env.CARAER_API_BASE_URL ||
    "https://api.caraer.com/api";
  return String(raw).replace(/\/$/, "");
}

function maxEventsFrom(settings) {
  const raw = settings && settings.max_events;
  const n = parseInt(String(raw == null ? "20" : raw), 10);
  if (!Number.isFinite(n) || n < 1) return 20;
  return Math.min(n, 100);
}

function inboxLabelFrom(settings) {
  const label = settings && settings.inbox_label;
  if (label == null || String(label).trim() === "") return "Default inbox";
  return String(label).trim();
}

/** Prefer the inbound JSON body over the Caraer envelope when present. */
function inboundPayload(body) {
  if (!body || typeof body !== "object") return {};
  if (body.payload && typeof body.payload === "object") {
    if (body.payload.body != null) return body.payload.body;
    return body.payload;
  }
  if (body.body != null && typeof body.body === "object") return body.body;
  return body;
}

async function caraerFetch(apiBase, installationToken, path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${installationToken}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch (_) {
    json = { raw: text };
  }
  if (!response.ok) {
    const err = new Error(
      `Caraer API ${response.status}: ${
        typeof json === "object" ? JSON.stringify(json) : text
      }`
    );
    err.status = response.status;
    err.body = json;
    throw err;
  }
  return json;
}

async function getState(apiBase, token, appUuid) {
  const res = await caraerFetch(
    apiBase,
    token,
    `/v2/apps/${encodeURIComponent(appUuid)}/installation/state`
  );
  return (res && res.data) || {};
}

async function putState(apiBase, token, appUuid, patch) {
  return caraerFetch(
    apiBase,
    token,
    `/v2/apps/${encodeURIComponent(appUuid)}/installation/state`,
    { method: "PUT", body: JSON.stringify(patch || {}) }
  );
}

module.exports = {
  parseBody,
  flattenSettings,
  apiBaseFrom,
  maxEventsFrom,
  inboxLabelFrom,
  inboundPayload,
  getState,
  putState,
};
