import { DialogCloseButton } from "../common/DialogCloseButton";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { AgentIcon } from "./AgentIcon";
import { ModalSurface } from "../common/ModalSurface";
import { Button } from "../common";

const AGENT_ICON_EMOJIS: { emoji: string; labelKey: string }[] = [
  { emoji: "✨", labelKey: "personaPresets.emojiSparkles" },
  { emoji: "🤖", labelKey: "personaPresets.emojiRobot" },
  { emoji: "🎓", labelKey: "personaPresets.emojiAcademic" },
  { emoji: "💻", labelKey: "personaPresets.emojiCoding" },
  { emoji: "✍️", labelKey: "personaPresets.emojiWriting" },
  { emoji: "🛡️", labelKey: "personaPresets.emojiSecurity" },
  { emoji: "📊", labelKey: "personaPresets.emojiData" },
  { emoji: "⚡", labelKey: "personaPresets.emojiProductivity" },
  { emoji: "📦", labelKey: "personaPresets.emojiGeneral" },
  { emoji: "🎨", labelKey: "personaPresets.emojiArt" },
  { emoji: "🎵", labelKey: "personaPresets.emojiMusic" },
  { emoji: "📚", labelKey: "personaPresets.emojiLiterature" },
  { emoji: "🧠", labelKey: "personaPresets.emojiIntelligence" },
  { emoji: "🔬", labelKey: "personaPresets.emojiScience" },
  { emoji: "💬", labelKey: "personaPresets.emojiChat" },
  { emoji: "🌟", labelKey: "personaPresets.emojiStar" },
];

interface AgentIconSelectProps {
  value: string;
  onChange: (value: string) => void;
}

export const AgentIconSelect = React.memo(function AgentIconSelect({
  value,
  onChange,
}: AgentIconSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const icon = value.trim();
  const selectedIcon = !icon || icon === "Bot" ? "🤖" : icon;

  return (
    <>
      <Button
        size="sm"
        aria-label={t("personaPresets.pickIcon")}
        aria-haspopup="dialog"
        aria-expanded={open}
        leftIcon={<AgentIcon icon={value || undefined} size={16} />}
        onClick={() => setOpen((current) => !current)}
      >
        {t("personaPresets.pickIcon", "选择图标")}
      </Button>

      <ModalSurface
        layer={1200}
        open={open}
        onClose={() => setOpen(false)}
        label={t("personaPresets.pickIcon")}
        className="modal-size-sm"
      >
        <div className="w-full rounded-2xl bg-theme-bg-card p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-16 font-semibold text-theme-text">
              {t("personaPresets.pickIcon")}
            </h2>
            <DialogCloseButton onClick={() => setOpen(false)} />
          </div>
          <div className="grid grid-cols-4 gap-2">
            {AGENT_ICON_EMOJIS.map((item) => (
              <Button
                key={item.emoji}
                variant={selectedIcon === item.emoji ? "secondary" : "ghost"}
                size="lg"
                aria-label={t(item.labelKey)}
                aria-pressed={selectedIcon === item.emoji}
                onClick={() => {
                  onChange(item.emoji);
                  setOpen(false);
                }}
              >
                <AgentIcon icon={item.emoji} size={24} />
              </Button>
            ))}
          </div>
        </div>
      </ModalSurface>
    </>
  );
});
