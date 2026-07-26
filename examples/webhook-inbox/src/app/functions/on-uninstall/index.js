const { parseBody } = require("./shared");

exports.handler = async (req, res) => {
  const body = parseBody(req);
  return res.status(200).json({
    ok: true,
    event: body.event || "Uninstalled",
    appUuid: body.appUuid || null,
  });
};
