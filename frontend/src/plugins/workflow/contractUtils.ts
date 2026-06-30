export type WorkflowInputDraftStatus = {
  message: string;
  messageKey?: string;
  messageValues?: Record<string, string>;
  parsed?: Record<string, unknown>;
};

type SampleValueOptions = {
  required?: boolean;
  depth?: number;
  fallbackText?: string;
};

function schemaObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function schemaProperties(schema: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const properties = schema?.properties;
  return properties && typeof properties === "object" && !Array.isArray(properties)
    ? (properties as Record<string, unknown>)
    : {};
}

function schemaRequiredFields(schema: Record<string, unknown> | null | undefined): Set<string> {
  return new Set(
    (Array.isArray(schema?.required) ? schema.required : [])
      .map((field) => String(field).trim())
      .filter(Boolean),
  );
}

function schemaPath(parent: string, field: string): string {
  return parent ? `${parent}.${field}` : field;
}

type WorkflowSchemaFieldLabelOptions = {
  nested?: boolean;
  limit?: number;
  prefix?: string;
};

export type WorkflowSchemaFieldDescriptor = {
  field: string;
  type: string;
};

export type WorkflowCallableInterfaceLabels = {
  entry: string;
  entrySchema: string;
  exit: string;
  exitSchema: string;
  schema: string;
  version: string;
};

function workflowInterfaceObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function workflowInterfaceText(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function workflowInterfaceToolField(tool: unknown, field: unknown): string {
  const toolName = workflowInterfaceText(tool);
  const fieldName = workflowInterfaceText(field);
  if (toolName && fieldName) return `${toolName}.${fieldName}`;
  return toolName || fieldName;
}

export function workflowCallableInterfaceLabels(interfacePayload: unknown): WorkflowCallableInterfaceLabels {
  const payload = workflowInterfaceObject(interfacePayload);
  const entry = workflowInterfaceObject(payload.entry);
  const exit = workflowInterfaceObject(payload.exit);
  const schema = workflowInterfaceObject(payload.schema);
  return {
    entry: workflowInterfaceToolField(entry.tool, entry.argument) || "workflow_run.input",
    entrySchema: workflowInterfaceToolField(entry.schema_tool, entry.schema_field) || "workflow_get_schema.input_schema",
    exit: workflowInterfaceText(exit.field) || "output",
    exitSchema: workflowInterfaceToolField(exit.schema_tool, exit.schema_field) || "workflow_get_schema.output_schema",
    schema: workflowInterfaceText(schema.tool) || "workflow_get_schema",
    version: workflowInterfaceText(schema.version_id),
  };
}

function workflowSchemaFieldType(schema: Record<string, unknown>): string {
  if (typeof schema.type === "string" && schema.type) return schema.type;
  if (Array.isArray(schema.type)) {
    return schema.type.map((item) => String(item)).filter(Boolean).join("|") || "unknown";
  }
  if (schema.properties && typeof schema.properties === "object" && !Array.isArray(schema.properties)) {
    return "object";
  }
  if (schema.items && typeof schema.items === "object" && !Array.isArray(schema.items)) {
    return "array";
  }
  return "unknown";
}

export function workflowSchemaFieldDescriptors(
  schema: Record<string, unknown> | null | undefined,
  options: WorkflowSchemaFieldLabelOptions = {},
): WorkflowSchemaFieldDescriptor[] {
  const properties = schemaProperties(schema);
  const descriptors = Object.entries(properties).flatMap(([name, rawSchema]) => {
    const fieldSchema = schemaObject(rawSchema);
    const fieldPath = schemaPath(options.prefix ?? "", name);
    const type = workflowSchemaFieldType(fieldSchema);
    if (options.nested && type === "object") {
      const nested = workflowSchemaFieldDescriptors(fieldSchema, {
        nested: true,
        prefix: fieldPath,
      });
      return nested.length > 0 ? nested : [{ field: fieldPath, type }];
    }
    if (options.nested && type === "array") {
      const itemSchema = schemaObject(fieldSchema.items);
      const nested = workflowSchemaFieldDescriptors(itemSchema, {
        nested: true,
        prefix: `${fieldPath}[]`,
      });
      return nested.length > 0 ? nested : [{ field: fieldPath, type }];
    }
    return [{ field: fieldPath, type }];
  });
  return typeof options.limit === "number" ? descriptors.slice(0, options.limit) : descriptors;
}

export function workflowSchemaFieldLabels(
  schema: Record<string, unknown> | null | undefined,
  options: WorkflowSchemaFieldLabelOptions = {},
): string[] {
  return workflowSchemaFieldDescriptors(schema, options).map(
    (descriptor) => `${descriptor.field}: ${descriptor.type}`,
  );
}

export function workflowOutputPathValue(output: Record<string, unknown>, path: string): unknown {
  if (!path) return undefined;

  function resolve(current: unknown, segments: string[]): unknown {
    if (segments.length === 0) return current;
    const [segment, ...rest] = segments;
    if (segment.endsWith("[]")) {
      const key = segment.slice(0, -2);
      if (!current || typeof current !== "object" || Array.isArray(current)) return undefined;
      const items = (current as Record<string, unknown>)[key];
      if (!Array.isArray(items)) return undefined;
      for (const item of items) {
        const value = resolve(item, rest);
        if (value !== undefined && value !== null && value !== "" && !(Array.isArray(value) && value.length === 0)) {
          return value;
        }
      }
      return undefined;
    }
    if (!current || typeof current !== "object" || Array.isArray(current)) return undefined;
    return resolve((current as Record<string, unknown>)[segment], rest);
  }

  return resolve(output, path.split("."));
}

export function workflowInputExpectedTypes(rawType: unknown): string[] {
  const aliases: Record<string, string> = {
    str: "string",
    string: "string",
    text: "string",
    paragraph: "string",
    select: "string",
    email: "string",
    url: "string",
    uri: "string",
    int: "integer",
    integer: "integer",
    float: "number",
    double: "number",
    number: "number",
    bool: "boolean",
    boolean: "boolean",
    array: "array",
    list: "array",
    object: "object",
    dict: "object",
    map: "object",
  };
  const rawTypes = Array.isArray(rawType) ? rawType : [rawType];
  return Array.from(
    new Set(
      rawTypes
        .map((item) => aliases[String(item || "").trim().toLowerCase()])
        .filter((item): item is string => Boolean(item)),
    ),
  );
}

function workflowInputMatchesType(value: unknown, expectedTypes: string[]): boolean {
  return expectedTypes.some((expectedType) => {
    if (expectedType === "string") return typeof value === "string";
    if (expectedType === "integer") return typeof value === "number" && Number.isInteger(value);
    if (expectedType === "number") return typeof value === "number" && Number.isFinite(value);
    if (expectedType === "boolean") return typeof value === "boolean";
    if (expectedType === "array") return Array.isArray(value);
    if (expectedType === "object") return Boolean(value) && typeof value === "object" && !Array.isArray(value);
    return true;
  });
}

export function sampleWorkflowInputValue(
  field: string,
  schema: Record<string, unknown>,
  options: SampleValueOptions = {},
): unknown {
  const required = options.required ?? false;
  const depth = options.depth ?? 0;
  const fallbackText = options.fallbackText ?? "";
  if (Object.prototype.hasOwnProperty.call(schema, "default")) return schema.default;
  if (Array.isArray(schema.enum) && schema.enum.length > 0) return schema.enum[0];
  const type = workflowInputExpectedTypes(schema.type)[0] ?? schema.type;
  if (type === "array") {
    const minItems = typeof schema.minItems === "number" && Number.isFinite(schema.minItems)
      ? Math.max(0, Math.floor(schema.minItems))
      : 0;
    const itemsSchema = schemaObject(schema.items);
    if (!required && minItems < 1) return [];
    const sampleCount = Math.min(Math.max(1, minItems), 3);
    return Array.from({ length: sampleCount }, () =>
      sampleWorkflowInputValue(field, itemsSchema, {
        required: true,
        depth: depth + 1,
        fallbackText,
      }),
    );
  }
  if (type === "object") {
    if (depth > 4) return {};
    const properties = schemaProperties(schema);
    const requiredFields = schemaRequiredFields(schema);
    return Object.fromEntries(
      Object.entries(properties).map(([childField, rawChildSchema]) => [
        childField,
        sampleWorkflowInputValue(childField, schemaObject(rawChildSchema), {
          required: requiredFields.has(childField),
          depth: depth + 1,
          fallbackText,
        }),
      ]),
    );
  }
  if (type === "boolean") return false;
  if (type === "integer" || type === "number") return 0;
  if (field === "query" || field === "message" || field === "input") return fallbackText;
  return "";
}

export function sampleWorkflowInputFromSchema(
  schema: Record<string, unknown> | null | undefined,
  fallbackText: string,
): Record<string, unknown> {
  const properties = schemaProperties(schema);
  if (Object.keys(properties).length === 0) {
    return { message: fallbackText };
  }
  const requiredFields = schemaRequiredFields(schema);
  return Object.fromEntries(
    Object.entries(properties).map(([field, rawSchema]) => [
      field,
      sampleWorkflowInputValue(field, schemaObject(rawSchema), {
        required: requiredFields.has(field),
        fallbackText,
      }),
    ]),
  );
}

function isEmptyInputValue(value: unknown): boolean {
  if (value == null || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
}

export function missingWorkflowInputFieldsForSchema(
  schema: Record<string, unknown> | null | undefined,
  value: unknown,
  path = "",
): string[] {
  const properties = schemaProperties(schema);
  const requiredFields = schemaRequiredFields(schema);
  const objectValue = value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
  const missing: string[] = [];
  for (const field of requiredFields) {
    const fieldSchema = schemaObject(properties[field]);
    const fieldPath = schemaPath(path, field);
    if (Object.prototype.hasOwnProperty.call(fieldSchema, "default")) continue;
    if (isEmptyInputValue(objectValue[field])) {
      missing.push(fieldPath);
    }
  }
  for (const [field, rawSchema] of Object.entries(properties)) {
    const fieldValue = objectValue[field];
    if (isEmptyInputValue(fieldValue)) continue;
    const fieldSchema = schemaObject(rawSchema);
    const fieldPath = schemaPath(path, field);
    missing.push(...missingWorkflowInputFieldsForSchema(fieldSchema, fieldValue, fieldPath));
    const itemsSchema = schemaObject(fieldSchema.items);
    if (Array.isArray(fieldValue) && Object.keys(itemsSchema).length > 0) {
      fieldValue.forEach((item, index) => {
        missing.push(...missingWorkflowInputFieldsForSchema(itemsSchema, item, `${fieldPath}[${index}]`));
      });
    }
  }
  return missing;
}

export function workflowInputSchemaError(
  schema: Record<string, unknown> | null | undefined,
  value: unknown,
  path = "",
): WorkflowInputDraftStatus | null {
  const properties = schemaProperties(schema);
  const objectValue = value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
  for (const [field, rawSchema] of Object.entries(properties)) {
    const fieldValue = objectValue[field];
    if (isEmptyInputValue(fieldValue)) continue;
    const fieldSchema = schemaObject(rawSchema);
    const fieldPath = schemaPath(path, field);
    const expectedTypes = workflowInputExpectedTypes(fieldSchema.type);
    if (expectedTypes.length > 0 && !workflowInputMatchesType(fieldValue, expectedTypes)) {
      return {
        message: `Input type mismatch: ${fieldPath} must be ${expectedTypes.join(" or ")}`,
        messageKey: "workflowPlugin.validation.inputTypeMismatch",
        messageValues: { field: fieldPath, types: expectedTypes.join(" / ") },
      };
    }
    if (
      Array.isArray(fieldSchema.enum)
      && fieldSchema.enum.length > 0
      && !fieldSchema.enum.some((option) => option === fieldValue)
    ) {
      return {
        message: `Input option mismatch: ${fieldPath}`,
        messageKey: "workflowPlugin.validation.inputOptionMismatch",
        messageValues: { field: fieldPath },
      };
    }
    const nestedError = workflowInputSchemaError(fieldSchema, fieldValue, fieldPath);
    if (nestedError) return nestedError;
    const itemsSchema = schemaObject(fieldSchema.items);
    if (Array.isArray(fieldValue) && Object.keys(itemsSchema).length > 0) {
      for (let index = 0; index < fieldValue.length; index += 1) {
        const itemError = workflowInputSchemaError(itemsSchema, fieldValue[index], `${fieldPath}[${index}]`);
        if (itemError) return itemError;
      }
    }
  }
  return null;
}

export function workflowInputDraftStatus(
  draft: string,
  schema: Record<string, unknown> | null | undefined,
): WorkflowInputDraftStatus {
  let parsed: unknown;
  try {
    parsed = JSON.parse(draft);
  } catch {
    return {
      message: "Invalid JSON",
      messageKey: "workflowPlugin.validation.invalidJson",
    };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {
      message: "Input must be a JSON object",
      messageKey: "workflowPlugin.validation.inputObjectRequired",
    };
  }
  const payload = parsed as Record<string, unknown>;
  const missing = Array.from(new Set(missingWorkflowInputFieldsForSchema(schema, payload)));
  if (missing.length > 0) {
    return {
      message: `Missing required input: ${missing.join(", ")}`,
      messageKey: "workflowPlugin.validation.missingRequiredInput",
      messageValues: { fields: missing.join(", ") },
    };
  }
  const schemaError = workflowInputSchemaError(schema, payload);
  if (schemaError) return schemaError;
  return { message: "", parsed: payload };
}

export function workflowInputDraftMessage(
  status: WorkflowInputDraftStatus | null | undefined,
  translate: (key: string, values?: Record<string, string>) => string,
): string {
  if (!status?.message) return "";
  return status.messageKey ? translate(status.messageKey, status.messageValues) : status.message;
}
