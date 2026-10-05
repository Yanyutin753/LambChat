import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import { Button, IconButton, Input, Select } from "../common";
import type { JsonSchema, JsonSchemaField } from "../../types/settings";

interface JsonSchemaEditorProps {
  value: object;
  schema: JsonSchema;
  disabled: boolean;
  onChange: (value: object) => void;
}

function getFieldLayoutClass(field: JsonSchemaField): string {
  if (field.layout_width === "compact") return "json-schema-field--compact";
  if (field.layout_width === "full") return "json-schema-field--full";
  return field.type === "toggle" || field.type === "number"
    ? "json-schema-field--compact"
    : "json-schema-field--full";
}

function FieldInput({
  field,
  value,
  disabled,
  onChange,
  index,
  hideLabel,
}: {
  field: JsonSchemaField;
  value: string | number | boolean;
  disabled: boolean;
  onChange: (val: string | number | boolean) => void;
  index: number;
  hideLabel: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const label = t(field.label);
  const accessibleLabel = `${label} ${index + 1}`;

  if (field.type === "toggle") {
    return (
      <div className="flex min-h-11 items-center gap-2 text-14 text-theme-text">
        <span>{label}</span>
        <button
          type="button"
          role="switch"
          aria-checked={Boolean(value)}
          aria-label={accessibleLabel}
          disabled={disabled}
          onClick={() => onChange(!value)}
          className="json-schema-switch"
        >
          <span />
        </button>
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <label
        htmlFor={id}
        className={
          hideLabel
            ? "sr-only"
            : "mb-1 block text-12 font-medium text-theme-text-secondary"
        }
      >
        {label}
        {field.required && (
          <span className="ml-0.5 text-theme-error" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {field.type === "select" && field.options ? (
        <Select
          ariaLabel={accessibleLabel}
          value={String(value ?? "")}
          disabled={disabled}
          onChange={onChange}
          options={field.options.map((opt) => ({ value: opt, label: opt }))}
          triggerClassName="min-h-11"
        />
      ) : (
        <Input
          id={id}
          aria-label={accessibleLabel}
          aria-required={field.required}
          type={
            field.type === "password"
              ? "password"
              : field.type === "number"
                ? "number"
                : "text"
          }
          value={value == null ? "" : String(value)}
          disabled={disabled}
          placeholder={field.placeholder}
          onChange={(event) =>
            onChange(
              field.type === "number"
                ? Number(event.target.value)
                : event.target.value,
            )
          }
          className="min-h-11 w-full text-14"
        />
      )}
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
  onChange: (value: unknown[]) => void;
}) {
  const { t } = useTranslation();
  const itemLabel = schema.item_label
    ? t(schema.item_label)
    : t("settings.item", "Item");
  const compact =
    schema.fields.length === 2 &&
    schema.fields[0].layout_width === "compact" &&
    schema.fields[1].layout_width === "full";

  return (
    <div
      className={
        compact
          ? "json-schema-list json-schema-list--compact"
          : "json-schema-list"
      }
    >
      {value.length === 0 ? (
        <p className="py-5 text-13 text-theme-text-secondary">
          {t("settingDesc.JSON_SCHEMA_EMPTY")}
        </p>
      ) : (
        compact && (
          <div className="json-schema-columns" aria-hidden="true">
            {schema.fields.map((field) => (
              <span key={field.name} className={getFieldLayoutClass(field)}>
                {t(field.label)}
                {field.required && (
                  <span className="ml-0.5 text-theme-error">*</span>
                )}
              </span>
            ))}
            {!disabled && <span className="w-11 shrink-0" />}
          </div>
        )
      )}
      {value.map((item, index) => (
        <div key={index} className="json-schema-row">
          {schema.fields.map((field) => (
            <div key={field.name} className={getFieldLayoutClass(field)}>
              <FieldInput
                field={field}
                index={index}
                hideLabel={compact}
                value={
                  (item as Record<string, unknown>)[field.name] as
                    string | number | boolean
                }
                disabled={disabled}
                onChange={(nextValue) => {
                  const next = [...value];
                  next[index] = {
                    ...(item as Record<string, unknown>),
                    [field.name]: nextValue,
                  };
                  onChange(next);
                }}
              />
            </div>
          ))}
          {!disabled && (
            <IconButton
              onClick={() =>
                onChange(value.filter((_, itemIndex) => itemIndex !== index))
              }
              className="json-schema-remove"
              icon={<Trash2 size={16} />}
              size="sm"
              aria-label={`${t("common.delete")} ${itemLabel} ${index + 1}`}
              title={`${t("common.delete")} ${itemLabel} ${index + 1}`}
            />
          )}
        </div>
      ))}
      {!disabled && (
        <Button
          onClick={() => {
            const item: Record<string, unknown> = {};
            for (const field of schema.fields) {
              item[field.name] =
                field.type === "toggle"
                  ? false
                  : field.type === "number"
                    ? 0
                    : "";
            }
            onChange([...value, item]);
          }}
          variant="ghost"
          size="sm"
          leftIcon={<Plus size={15} />}
          className="mt-3 min-h-11 text-13"
        >
          {t("settingDesc.JSON_SCHEMA_ADD_ITEM")} {itemLabel}
        </Button>
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
  onChange: (value: Record<string, unknown[]>) => void;
}) {
  const { t, i18n } = useTranslation();
  const keys = schema.key_options || Object.keys(value);
  const [selectedKey, setSelectedKey] = useState(i18n.language?.split("-")[0]);
  const activeKey = keys.includes(selectedKey) ? selectedKey : keys[0];
  const id = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIndex = keys.indexOf(activeKey);

  return (
    <div className="json-schema-editor">
      <div
        role="tablist"
        aria-label={
          schema.key_label ? t(schema.key_label) : t("settings.key", "Key")
        }
        className="json-schema-tabs"
      >
        {keys.map((key, index) => (
          <button
            key={key}
            ref={(node) => {
              tabs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${index}`}
            aria-selected={key === activeKey}
            aria-controls={`${id}-panel`}
            tabIndex={key === activeKey ? 0 : -1}
            onClick={() => setSelectedKey(key)}
            onKeyDown={(event) => {
              let next: number;
              if (event.key === "ArrowRight") next = (index + 1) % keys.length;
              else if (event.key === "ArrowLeft")
                next = (index - 1 + keys.length) % keys.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = keys.length - 1;
              else return;
              event.preventDefault();
              setSelectedKey(keys[next]);
              tabs.current[next]?.focus();
            }}
          >
            <span className="uppercase">{key}</span>
            <span
              aria-hidden="true"
              className="text-11 tabular-nums opacity-60"
            >
              {value[key]?.length || 0}
            </span>
          </button>
        ))}
      </div>
      {activeKey !== undefined && (
        <div
          role="tabpanel"
          id={`${id}-panel`}
          aria-labelledby={`${id}-tab-${activeIndex}`}
          tabIndex={0}
          className="json-schema-tabpanel"
        >
          <ArrayEditor
            value={value[activeKey] || []}
            schema={schema}
            disabled={disabled}
            onChange={(items) => onChange({ ...value, [activeKey]: items })}
          />
        </div>
      )}
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
        onChange={onChange}
      />
    );
  }
  if (schema.type === "object" && schema.value_type === "array") {
    return (
      <ObjectArrayEditor
        value={(value as Record<string, unknown[]>) || {}}
        schema={schema}
        disabled={disabled}
        onChange={onChange}
      />
    );
  }
  return null;
}
