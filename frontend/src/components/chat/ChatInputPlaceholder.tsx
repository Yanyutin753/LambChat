import { useTranslation } from "react-i18next";
import { resolveComposerPlaceholder } from "./composerPlaceholder";

export function ChatInputPlaceholder({
  canSend,
  disabled,
  sendBlocked,
  isLoading,
  mentionMode,
  mentionEnabled,
  selectedId,
  sandbox,
}: Parameters<typeof resolveComposerPlaceholder>[0] & {
  disabled?: boolean;
  mentionEnabled: boolean;
  selectedId?: string | null;
}) {
  const { t } = useTranslation();
  const showMentionHint =
    canSend && !disabled && !sendBlocked && !isLoading && mentionEnabled && !!selectedId;

  return (
    <>
      {t(resolveComposerPlaceholder({ canSend, mentionMode, isLoading, sendBlocked, sandbox }))}
      {showMentionHint && (
        <span className="composer-placeholder-hint">
          {" "}{t(mentionMode === "team" ? "chat.teamMentionHint" : "chat.personaMentionHint")}
        </span>
      )}
    </>
  );
}
