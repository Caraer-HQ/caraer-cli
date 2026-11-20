export type Values = Record<string, unknown>;

export type Field = {
  name?: string;
  label?: string;
  group?: string;
  type?: string;
  fields?: Field[];
  itemFields?: Field[];
  defaultValue?: unknown;
  options?: { name: string; label: string }[];
};

export function recordValue(value: unknown): value is Values {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Fill stored values from declared defaults; keep underlying property and record references. */
export function materializeModuleFields(definitions: Field[], overrides: Values): Values {
  const result: [string, unknown][] = [];
  function visit(fields: Field[]) {
    for (const field of fields) {
      if (field.fields) visit(field.fields);
      const { name, itemFields } = field;
      if (!name) continue;
      const fallback = field.defaultValue ?? (field.type === 'REPEATABLE' ? [] : null);
      const stored = Object.hasOwn(overrides, name) ? overrides[name] : undefined;
      const value = stored ?? fallback;
      result.push([
        name,
        field.type === 'REPEATABLE'
          ? Array.isArray(value)
            ? value.filter(recordValue).map(item => itemFields?.length
              ? materializeModuleFields(itemFields, item)
              : item)
            : []
          : value,
      ]);
    }
  }
  visit(definitions);
  return Object.fromEntries(result);
}
