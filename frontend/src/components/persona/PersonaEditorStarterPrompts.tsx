import { useTranslation } from "react-i18next";
import { X, Plus, Sparkles } from "lucide-react";

interface StarterPromptsEditorProps {
  prompts: { icon: string; text: string }[];
  onChange: (
    updater: (
      prev: { icon: string; text: string }[],
    ) => { icon: string; text: string }[],
  ) => void;
}

export function StarterPromptsEditor({
  prompts,
  onChange,
}: StarterPromptsEditorProps) {
  const { t } = useTranslation();

  return (
    <div className="ppe-field">
      <label className="ppe-label">
        <Sparkles size={13} className="ppe-label-icon" />
        {t("personaPresets.starterPrompts", "开场提示词")}
      </label>
      <div className="ppe-starter-list">
        {prompts.map((prompt, index) => (
          <div key={index} className="ppe-starter-row">
            <input
              aria-label={`${t("personaPresets.starterIcon")} ${index + 1}`}
              value={prompt.icon}
              onChange={(e) =>
                onChange((prev) =>
                  prev.map((item, i) =>
                    i === index ? { ...item, icon: e.target.value } : item,
                  ),
                )
              }
              className="ppe-input ppe-starter-icon"
              placeholder={t("personaPresets.starterIcon", "图标")}
            />
            <input
              aria-label={`${t("personaPresets.starterPrompts")} ${index + 1}`}
              value={prompt.text}
              onChange={(e) =>
                onChange((prev) =>
                  prev.map((item, i) =>
                    i === index ? { ...item, text: e.target.value } : item,
                  ),
                )
              }
              className="ppe-input ppe-starter-text"
              placeholder={t(
                "personaPresets.starterPromptPlaceholder",
                '输入提示词，或使用 {"zh":"...","en":"..."}',
              )}
            />
            <button
              type="button"
              className="ppe-starter-remove"
              onClick={() =>
                onChange((prev) => prev.filter((_, i) => i !== index))
              }
              aria-label={`${t("common.delete")} ${t(
                "personaPresets.starterPrompts",
              )} ${index + 1}`}
              title={t("common.delete", "删除")}
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="ppe-starter-add"
        onClick={() => onChange((prev) => [...prev, { icon: "", text: "" }])}
      >
        <Plus size={13} />
        {t("personaPresets.addStarterPrompt", "添加开场提示词")}
      </button>
    </div>
  );
}
