const { contextFrom, ok } = require("../shared");

// event.type is "property_changed". <setting:field_map.email> is the property
// mapped to the email fieldName.
exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  ok(res, {
    functionName: "field-map",
    eventType: ctx.eventType,
    record: ctx.record,
    propertyName: ctx.body.propertyName || null,
  });
};

exports.manifest = {
  description: "Fires when a mapped property on the field_map object changes.",
  webhooks: [
    {
      topic: "record.<setting:field_map.objectName>.property_changed.<setting:field_map.email>",
    },
  ],
};
