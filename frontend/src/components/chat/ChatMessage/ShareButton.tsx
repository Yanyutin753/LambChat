/**
 * ShareButton - Standalone share button component for ChatMessage
 */

import { useState } from "react";
import { Share2 } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { ShareDialog } from "../../share/ShareDialog";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";

interface ShareButtonProps {
  sessionId: string;
  runId?: string;
  sessionName?: string;
  className?: string;
  isLastMessage?: boolean;
}

export function ShareButton({
  sessionId,
  runId,
  sessionName,
  className,
  isLastMessage,
}: ShareButtonProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [shareDialogOpen, setShareDialogOpen] = useState(false);

  // Check if user has share permission
  const hasSharePermission = user?.permissions?.includes(
    Permission.SESSION_SHARE,
  );

  if (!hasSharePermission) {
    return null;
  }

  return (
    <>
      <button
        onClick={() => setShareDialogOpen(true)}
        className={clsx(
          "flex items-center justify-center rounded-md p-1.5 transition-all",
          !isLastMessage && "opacity-0 group-hover:opacity-100",
          "text-gray-400 dark:text-stone-500 hover:bg-gray-200 dark:hover:bg-stone-700 hover:text-gray-600 dark:hover:text-stone-300",
          className,
        )}
        title={t("share.title")}
      >
        <Share2 size={16} />
      </button>
      <ShareDialog
        isOpen={shareDialogOpen}
        onClose={() => setShareDialogOpen(false)}
        sessionId={sessionId}
        sessionName={sessionName || t("sidebar.newChat")}
        currentRunId={runId}
      />
    </>
  );
}
