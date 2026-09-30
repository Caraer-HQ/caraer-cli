const { contextFrom, ok } = require("../shared");

// Date-due body uses the same USER_FRIENDLY record envelope as a record
// webhook. event.type is "date_due". propertyName is the selected property.
exports.handler = async (req, res) => {
  const ctx = contextFrom(req);
  ok(res, {
    functionName: "due-date",
    eventType: ctx.eventType,
    record: ctx.record,
    propertyName: ctx.body.propertyName || null,
  });
};

exports.manifest = {
  description: "Fires for the due date chosen in the due_date setting.",
  webhooks: [
    {
      topic: "record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>",
      label: "Due date",
      webhookFormat: "USER_FRIENDLY",
      triggerOffsetSeconds: 0,
    },
  ],
};
