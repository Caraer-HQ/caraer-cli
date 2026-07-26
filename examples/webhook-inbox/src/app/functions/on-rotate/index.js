const { parseBody } = require("./shared");

exports.handler = async (req, res) => {
  const body = parseBody(req);
  return res.status(200).json({
    ok: true,
    event: body.event || "Rotated",
    appUuid: body.appUuid || null,
  });
};
