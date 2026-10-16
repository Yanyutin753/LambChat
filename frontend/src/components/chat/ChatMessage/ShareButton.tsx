import { InteractiveIcon } from "../../common/InteractiveIcon";
/**
 * ShareButton - Standalone share button component for ChatMessage
 */

import { useState } from "react";
import { Share2 } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { ShareDialog } from "../../share/ShareDialog";
import { Tooltip } from "../../common/Tooltip";
import { useAuth } from "../../../hooks/useAuth";
import { useSessionTitle } from "../../../hooks/useSessionTitle";
import { Permission } from "../../../types";

interface ShareButtonProps {
  sessionId: string;
  runId?: string;
  className?: string;
}

export function ShareButton({ sessionId, runId, className }: ShareButtonProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const sessionTitle = useSessionTitle(sessionId, {
    enabled: shareDialogOpen,
  });

  // Check if user has share permission
  const hasSharePermission = user?.permissions?.includes(
    Permission.SESSION_SHARE,
  );

  if (!hasSharePermission) {
    return null;
  }

  return (
    <>
      <Tooltip content={t("share.title")}>
        <button
          onClick={() => setShareDialogOpen(true)}
          aria-label={t("share.title")}
          className={clsx(
            "flex items-center justify-center rounded-md p-1.5 transition-all",
            "text-stone-400 dark:text-stone-500 hover:bg-theme-bg-hover dark:hover:bg-theme-bg-hover hover:text-stone-600 dark:hover:text-stone-300",
            className,
          )}
        >
          <InteractiveIcon>
            <Share2 size={16} />
          </InteractiveIcon>
        </button>
      </Tooltip>
      <ShareDialog
        isOpen={shareDialogOpen}
        onClose={() => setShareDialogOpen(false)}
        sessionId={sessionId}
        sessionName={sessionTitle || t("sidebar.newChat")}
        currentRunId={runId}
      />
    </>
  );
}
