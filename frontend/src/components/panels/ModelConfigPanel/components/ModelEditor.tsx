/**
 * Model editor row component
 */
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CSSProperties } from "react";
import type { ModelConfig } from "../../../../types";

interface ModelEditorProps {
  model: ModelConfig;
  onUpdate: (updated: ModelConfig) => void;
  onDelete: () => void;
  brandColor?: string;
}

export function ModelEditor({
  model,
  onUpdate,
  onDelete,
  brandColor,
}: ModelEditorProps) {
  const { t } = useTranslation();

  return (
    <div className="model-config-model-row group rounded-3xl p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div
            className="model-config-model-row__eyebrow"
            style={{ color: brandColor || "var(--theme-text-secondary)" }}
          >
            {t("modelConfig.modelEntry")}
          </div>
          <p className="model-config-model-row__caption">
            {t("modelConfig.modelDescriptionPlaceholder")}
          </p>
        </div>
        <button
          onClick={onDelete}
          className="model-config-icon-button model-config-icon-button--danger model-config-model-row__delete rounded-2xl p-2.5"
          aria-label={t("modelConfig.deleteModel")}
        >
          <Trash2 size={16} />
        </button>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* Model ID / Value */}
        <div className="model-config-field">
          <label
            className="model-config-field__label"
            style={{ color: brandColor || "var(--theme-text-secondary)" }}
          >
            {t("modelConfig.modelValuePlaceholder")}
          </label>
          <input
            type="text"
            value={model.value}
            onChange={(e) => onUpdate({ ...model, value: e.target.value })}
            className="model-config-input model-config-field__input px-3.5 py-3 text-sm"
            style={{
              color: "var(--theme-text)",
              ...(brandColor
                ? ({ "--tw-ring-color": `${brandColor}40` } as CSSProperties)
                : {}),
            }}
            placeholder={t("modelConfig.modelValuePlaceholder")}
          />
        </div>

        {/* Display Name */}
        <div className="model-config-field">
          <label
            className="model-config-field__label"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {t("modelConfig.modelLabelPlaceholder")}
          </label>
          <input
            type="text"
            value={model.label}
            onChange={(e) => onUpdate({ ...model, label: e.target.value })}
            className="model-config-input model-config-field__input px-3.5 py-3 text-sm"
            placeholder={t("modelConfig.modelLabelPlaceholder")}
          />
        </div>
      </div>

      <div className="mt-3 model-config-field">
        <label
          className="model-config-field__label"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {t("modelConfig.modelDescriptionPlaceholder")}
        </label>
        <input
          type="text"
          value={model.description || ""}
          onChange={(e) => onUpdate({ ...model, description: e.target.value })}
          className="model-config-input model-config-field__input w-full px-3.5 py-3 text-sm"
          placeholder={t("modelConfig.modelDescriptionPlaceholder")}
        />
      </div>
    </div>
  );
}
