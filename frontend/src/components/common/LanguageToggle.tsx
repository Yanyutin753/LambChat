import { useState, useRef, useCallback, useId } from "react";
import { useTranslation } from "react-i18next";
import { Languages, Check, AlertCircle } from "lucide-react";
import { useLanguagePreference } from "../../hooks/useLanguagePreference";
import { ResourceCardMenu } from "./ResourceCardMenu";
import { IconButton } from "./ui/IconButton";
import { LoadingSpinner } from "./LoadingSpinner";

const LANGUAGES = [
  { code: "en", nativeName: "English" },
  { code: "zh", nativeName: "中文" },
  { code: "ja", nativeName: "日本語" },
  { code: "ko", nativeName: "한국어" },
  { code: "ru", nativeName: "Русский" },
];
export function LanguageToggle({
  className,
  sync = true,
}: {
  className?: string;
  sync?: boolean;
}) {
  const { i18n, t } = useTranslation();
  const { languageState, selectLanguage, retryLanguage } =
    useLanguagePreference(sync);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(
    null,
  );
  const triggerRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback((restoreFocus = false) => {
    setPosition(null);
    if (restoreFocus) triggerRef.current?.querySelector("button")?.focus();
  }, []);
  return (
    <div ref={triggerRef}>
      <IconButton
        size="sm"
        icon={
          languageState === "saving" ? (
            <LoadingSpinner size="sm" />
          ) : languageState === "error" ? (
            <AlertCircle size={18} className="text-theme-error" />
          ) : (
            <Languages size={18} />
          )
        }
        className={`max-sm:!min-h-11 max-sm:!min-w-11 [@media(pointer:coarse)]:!min-h-11 [@media(pointer:coarse)]:!min-w-11 ${className ?? ""}`}
        title={t("common.language")}
        aria-label={t("common.language")}
        aria-description={
          languageState === "error"
            ? t("profile.preferenceSyncFailed")
            : undefined
        }
        aria-busy={languageState === "saving"}
        aria-expanded={Boolean(position)}
        aria-haspopup="menu"
        aria-controls={position ? id : undefined}
        onClick={(event) => {
          if (position) {
            close(true);
            return;
          }
          const rect = event.currentTarget.getBoundingClientRect();
          setPosition({ x: rect.right - 224, y: rect.bottom + 4 });
        }}
      />
      {position && (
        <ResourceCardMenu
          id={id}
          title={t("common.language")}
          position={position}
          onClose={close}
          actions={[
            ...(languageState === "error"
              ? [
                  {
                    label: `${t("common.retry")}: ${t("common.language")}`,
                    groupLabel: t("profile.preferenceSyncFailed"),
                    icon: <AlertCircle size={16} />,
                    onClick: retryLanguage,
                  },
                ]
              : []),
            ...LANGUAGES.map((lang) => {
              const checked = i18n.language.split("-")[0] === lang.code;
              return {
                label: lang.nativeName,
                checked,
                disabled: languageState === "saving",
                icon: (
                  <Check
                    size={16}
                    className={checked ? "" : "invisible"}
                    aria-hidden="true"
                  />
                ),
                onClick: () => {
                  selectLanguage(lang.code);
                },
              };
            }),
          ]}
        />
      )}
    </div>
  );
}
