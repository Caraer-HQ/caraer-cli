"use strict";

function parseBody(req) {
  if (!req || req.body == null) {
    return {};
  }
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
  if (!Array.isArray(schema)) {
    return out;
  }
  for (const field of schema) {
    if (!field || !field.name) {
      continue;
    }
    out[field.name] = field.value ?? field.defaultValue ?? null;
  }
  return out;
}

function objectNameFromSetting(value) {
  if (!value) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim().toLowerCase();
  }
  const name = value.internalName || value.name || value.objectName;
  return name ? String(name).trim().toLowerCase() : "";
}

function apiBase(body) {
  const raw =
    (body && body.caraerApiBase) ||
    process.env.CARAER_API_BASE ||
    "https://api.caraer.com/api";
  return String(raw).replace(/\/$/, "");
}

function contextFrom(req) {
  const body = parseBody(req);
  return {
    body,
    settings: flattenSettings(body.settingsSchema),
    apiBase: apiBase(body),
    token: body.installationToken,
    appUuid: body.appUuid,
    companyUuid: body.companyUuid,
    functionName: body.functionName,
    topic: body.topic || body.event || null,
  };
}

async function caraerFetch(ctx, path, options) {
  const opts = options || {};
  const url = `${ctx.apiBase}${path}`;
  const headers = {
    Authorization: `Bearer ${ctx.token}`,
    "Content-Type": "application/json",
    ...(opts.headers || {}),
  };
  if (ctx.companyUuid && !headers["X-Caraer-Company-Uuid"]) {
    headers["X-Caraer-Company-Uuid"] = ctx.companyUuid;
  }
  const response = await fetch(url, {
    method: opts.method || "GET",
    headers,
    body: opts.body == null ? undefined : JSON.stringify(opts.body),
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_) {
      data = { raw: text };
    }
  }
  return { ok: response.ok, status: response.status, data };
}

async function putState(ctx, payload) {
  return caraerFetch(
    ctx,
    `/v2/apps/${encodeURIComponent(ctx.appUuid)}/installation/state`,
    { method: "PUT", body: payload },
  );
}

async function runSql(ctx, statements) {
  return caraerFetch(
    ctx,
    `/v2/apps/${encodeURIComponent(ctx.appUuid)}/installation/db`,
    { method: "POST", body: { statements } },
  );
}

function ok(res, extra) {
  res.status(200).json({
    ok: true,
    layout: "2026.2.1",
    functionName: extra && extra.functionName,
    ...extra,
  });
}

module.exports = {
  contextFrom,
  flattenSettings,
  objectNameFromSetting,
  putState,
  runSql,
  ok,
};
