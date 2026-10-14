import { useTranslation } from "react-i18next";
import { AVATAR_EMOJIS } from "../persona/PersonaEditorTypes";
import { AgentAvatar } from "./AgentAvatar";
import { Button } from "./ui";

const GENERATED_AVATARS = Array.from(
  { length: 8 },
  (_, index) => `generated:avatar-${index + 1}`,
);

export function AvatarChoices({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <div>
        <p className="mb-2 text-12 text-theme-text-secondary">
          {t("personaPresets.generatedAvatars")}
        </p>
        <div className="grid grid-cols-4 gap-2">
          {GENERATED_AVATARS.map((avatar, index) => (
            <Button
              key={avatar}
              variant={value === avatar ? "secondary" : "ghost"}
              size="lg"
              aria-label={t("personaPresets.generatedAvatar", {
                number: index + 1,
              })}
              aria-pressed={value === avatar}
              onClick={() => onChange(avatar)}
            >
              <AgentAvatar avatar={avatar} size={32} />
            </Button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {AVATAR_EMOJIS.map((item) => (
          <Button
            key={item.emoji}
            variant={value === item.emoji ? "secondary" : "ghost"}
            size="lg"
            aria-label={t(item.labelKey)}
            aria-pressed={value === item.emoji}
            onClick={() => onChange(item.emoji)}
          >
            <AgentAvatar avatar={item.emoji} size={32} />
          </Button>
        ))}
      </div>
    </div>
  );
}
