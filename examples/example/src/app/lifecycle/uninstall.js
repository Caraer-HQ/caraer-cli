import { contextFrom, ok } from "../shared/index.js";

export const handler = async (req, res) => {
  const ctx = contextFrom(req);
  ok(res, {
    functionName: "uninstall",
    companyUuid: ctx.companyUuid,
  });
};

export const manifest = {
  lifecycle: "uninstall",
  topic: "app.uninstalled",
  label: "App uninstalled",
};
