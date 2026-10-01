/**
 * Options loader for the RECORD_OVERVIEW dialog field `channel`.
 * Caraer calls this with action "loadSettingOptions".
 */
export const handler = async (req, res) => {
  const body =
    typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  const query = String(body.query || "").trim().toLowerCase();
  const all = [
    { name: "email", label: "Email", helpText: "Send by email" },
    { name: "sms", label: "SMS" },
    { name: "in_app", label: "In app", preview: "Bell" },
  ];
  const options = query
    ? all.filter(
        (option) =>
          option.name.includes(query) || option.label.toLowerCase().includes(query),
      )
    : all;
  return res.status(200).json({ options, fieldName: body.fieldName });
};
