import { DialogCloseButton } from "../common/DialogCloseButton";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { AvatarChoices } from "../common/AvatarChoices";
import { AgentIcon } from "./AgentIcon";
import { ModalSurface } from "../common/ModalSurface";
import { Button } from "../common";

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
  const selectedIcon = icon === "Bot" ? "" : icon;

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
          <AvatarChoices
            value={selectedIcon}
            onChange={(avatar) => {
              onChange(avatar);
              setOpen(false);
            }}
          />
        </div>
      </ModalSurface>
    </>
  );
});
