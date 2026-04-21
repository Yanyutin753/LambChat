import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import type { JsonSchema, JsonSchemaField } from "../../types/settings";

interface JsonSchemaEditorProps {
  value: object;
  schema: JsonSchema;
  disabled: boolean;
  onChange: (value: object) => void;
}

function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: JsonSchemaField;
  value: string | number | boolean;
  disabled: boolean;
  onChange: (val: string | number | boolean) => void;
}) {
  const { t } = useTranslation();
  const label = t(field.label);

  if (field.type === "toggle") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <span className="text-stone-700 dark:text-stone-300">{label}</span>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(!value)}
          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
            value ? "bg-blue-500" : "bg-stone-300 dark:bg-stone-600"
          } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
              value ? "translate-x-4.5" : "translate-x-0.5"
            }`}
          />
        </button>
      </label>
    );
  }

  if (field.type === "select" && field.options) {
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-stone-600 dark:text-stone-400">
          {label}
        </label>
        <select
          value={String(value)}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 py-1.5 text-sm text-stone-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-stone-600 dark:text-stone-400">
        {label}
        {field.required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      <input
        type={
          field.type === "password"
            ? "password"
            : field.type === "number"
              ? "number"
              : "text"
        }
        value={value === undefined || value === null ? "" : String(value)}
        disabled={disabled}
        placeholder={field.placeholder}
        onChange={(e) => {
          if (field.type === "number") {
            onChange(Number(e.target.value));
          } else {
            onChange(e.target.value);
          }
        }}
        className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 py-1.5 text-sm text-stone-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
      />
    </div>
  );
}

function ArrayEditor({
  value,
  schema,
  disabled,
  onChange,
}: {
  value: unknown[];
  schema: JsonSchema;
  disabled: boolean;
  onChange: (val: unknown[]) => void;
}) {
  const { t } = useTranslation();
  const itemLabel = schema.item_label ? t(schema.item_label) : "Item";

  const addItem = () => {
    const newItem: Record<string, unknown> = {};
    for (const field of schema.fields) {
      if (field.type === "toggle") newItem[field.name] = false;
      else if (field.type === "number") newItem[field.name] = 0;
      else newItem[field.name] = "";
    }
    onChange([...value, newItem]);
  };

  const removeItem = (index: number) => {
    const next = [...value];
    next.splice(index, 1);
    onChange(next);
  };

  const updateItem = (
    index: number,
    fieldName: string,
    fieldValue: string | number | boolean,
  ) => {
    const next = [...value];
    next[index] = {
      ...(next[index] as Record<string, unknown>),
      [fieldName]: fieldValue,
    };
    onChange(next);
  };

  return (
    <div className="space-y-3">
      {value.length === 0 && (
        <p className="text-sm text-stone-400 dark:text-stone-500">
          {t("settingDesc.JSON_SCHEMA_EMPTY")}
        </p>
      )}
      {value.map((item, index) => (
        <div
          key={index}
          className="relative rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-secondary)] p-3"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
              {itemLabel} {index + 1}
            </span>
            {!disabled && (
              <button
                type="button"
                onClick={() => removeItem(index)}
                className="rounded p-1 text-stone-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {schema.fields.map((field) => (
              <FieldInput
                key={field.name}
                field={field}
                value={
                  (item as Record<string, unknown>)[field.name] as
                    | string
                    | number
                    | boolean
                }
                disabled={disabled}
                onChange={(val) => updateItem(index, field.name, val)}
              />
            ))}
          </div>
        </div>
      ))}
      {!disabled && (
        <button
          type="button"
          onClick={addItem}
          className="flex items-center gap-1.5 rounded-lg border border-dashed border-[var(--glass-border)] px-3 py-2 text-sm text-stone-500 hover:border-blue-400 hover:text-blue-500 dark:text-stone-400 dark:hover:border-blue-500 dark:hover:text-blue-400"
        >
          <Plus size={14} />
          {t("settingDesc.JSON_SCHEMA_ADD_ITEM")} {itemLabel}
        </button>
      )}
    </div>
  );
}

function ObjectArrayEditor({
  value,
  schema,
  disabled,
  onChange,
}: {
  value: Record<string, unknown[]>;
  schema: JsonSchema;
  disabled: boolean;
  onChange: (val: Record<string, unknown[]>) => void;
}) {
  const { t } = useTranslation();
  const keyLabel = schema.key_label ? t(schema.key_label) : "Key";
  const itemLabel = schema.item_label ? t(schema.item_label) : "Item";
  const keys = schema.key_options || Object.keys(value);

  return (
    <div className="space-y-4">
      {keys.map((key) => (
        <div key={key}>
          <div className="mb-2 flex items-center justify-between">
            <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600 dark:bg-stone-700 dark:text-stone-300">
              {keyLabel}: {key}
            </span>
          </div>
          <div className="space-y-2">
            {(value[key] || []).map((item, index) => (
              <div
                key={index}
                className="flex items-end gap-2 rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-secondary)] p-2"
              >
                {schema.fields.map((field) => (
                  <div key={field.name} className="flex-1">
                    <FieldInput
                      field={field}
                      value={
                        (item as Record<string, unknown>)[field.name] as
                          | string
                          | number
                          | boolean
                      }
                      disabled={disabled}
                      onChange={(val) => {
                        const next = { ...value };
                        const items = [...(next[key] || [])];
                        items[index] = {
                          ...(items[index] as Record<string, unknown>),
                          [field.name]: val,
                        };
                        next[key] = items;
                        onChange(next);
                      }}
                    />
                  </div>
                ))}
                {!disabled && (
                  <button
                    type="button"
                    onClick={() => {
                      const next = { ...value };
                      const items = [...(next[key] || [])];
                      items.splice(index, 1);
                      next[key] = items;
                      onChange(next);
                    }}
                    className="mb-0.5 rounded p-1 text-stone-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
            {!disabled && (
              <button
                type="button"
                onClick={() => {
                  const newItem: Record<string, unknown> = {};
                  for (const field of schema.fields) {
                    if (field.type === "toggle") newItem[field.name] = false;
                    else if (field.type === "number") newItem[field.name] = 0;
                    else newItem[field.name] = "";
                  }
                  const next = { ...value };
                  next[key] = [...(next[key] || []), newItem];
                  onChange(next);
                }}
                className="flex items-center gap-1.5 rounded-lg border border-dashed border-[var(--glass-border)] px-3 py-1.5 text-xs text-stone-500 hover:border-blue-400 hover:text-blue-500 dark:text-stone-400 dark:hover:border-blue-500 dark:hover:text-blue-400"
              >
                <Plus size={12} />
                {t("settingDesc.JSON_SCHEMA_ADD_ITEM")} {itemLabel}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function JsonSchemaEditor({
  value,
  schema,
  disabled,
  onChange,
}: JsonSchemaEditorProps) {
  if (schema.type === "array") {
    return (
      <ArrayEditor
        value={(value as unknown[]) || []}
        schema={schema}
        disabled={disabled}
        onChange={onChange as (val: unknown[]) => void}
      />
    );
  }

  if (schema.type === "object" && schema.value_type === "array") {
    return (
      <ObjectArrayEditor
        value={(value as Record<string, unknown[]>) || {}}
        schema={schema}
        disabled={disabled}
        onChange={onChange as (val: Record<string, unknown[]>) => void}
      />
    );
  }

  return null;
}
