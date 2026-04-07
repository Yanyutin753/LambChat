/**
 * Model editor row component
 */
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ModelConfig } from "../../../../types";

interface ModelEditorProps {
  model: ModelConfig;
  onUpdate: (updated: ModelConfig) => void;
  onDelete: () => void;
}

export function ModelEditor({ model, onUpdate, onDelete }: ModelEditorProps) {
  const { t } = useTranslation();
  return (
    <div
      className="flex items-center gap-3 rounded-xl border p-3 transition-colors"
      style={{
        borderColor: "var(--theme-border)",
        background: "var(--theme-bg-card)",
      }}
    >
      <input
        type="text"
        value={model.value}
        onChange={(e) => onUpdate({ ...model, value: e.target.value })}
        className="flex-1 min-w-0 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
        style={{
          border: "1px solid var(--theme-border)",
          background: "var(--theme-bg)",
          color: "var(--theme-text)",
        }}
        placeholder={t("modelConfig.modelValuePlaceholder")}
      />
      <input
        type="text"
        value={model.label}
        onChange={(e) => onUpdate({ ...model, label: e.target.value })}
        className="flex-1 min-w-0 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
        style={{
          border: "1px solid var(--theme-border)",
          background: "var(--theme-bg)",
          color: "var(--theme-text)",
        }}
        placeholder={t("modelConfig.modelLabelPlaceholder")}
      />
      <button
        onClick={onDelete}
        className="flex-shrink-0 p-2 text-stone-400 hover:text-red-500 dark:text-stone-500 dark:hover:text-red-400 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
      >
        <Trash2 size={16} />
      </button>
    </div>
  );
}
