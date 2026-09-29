const { contextFrom, ok } = require("../shared");

exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  ok(res, {
    functionName: "uninstall",
    companyUuid: ctx.companyUuid,
  });
};

exports.manifest = {
  lifecycle: "uninstall",
  topic: "app.uninstalled",
};
