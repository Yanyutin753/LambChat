import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getClientSandboxWorkspaceRoot,
  getOrCreateClientSandboxDeviceId,
  shouldStartClientSandboxService,
} from "../../services/clientSandbox/device";
import { startClientSandboxService } from "../../services/clientSandbox/ws";
import { enableClientSandboxPreference } from "../../services/clientSandbox/api";

interface ClientSandboxButtonProps {
  sessionId?: string | null;
}

const DEFAULT_WORKSPACE_ROOT = "~/LambChatWorkspace";

export function ClientSandboxButton(_props: ClientSandboxButtonProps) {
  const { t } = useTranslation();
  const [isDesktopSandboxAvailable, setIsDesktopSandboxAvailable] =
    useState(false);
  const [isEnabling, setIsEnabling] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);

  useEffect(() => {
    setIsDesktopSandboxAvailable(shouldStartClientSandboxService());
  }, []);

  const handleEnable = useCallback(async () => {
    if (isEnabling) return;
    setIsEnabling(true);
    try {
      const deviceId = getOrCreateClientSandboxDeviceId();
      const workspaceRoot =
        getClientSandboxWorkspaceRoot() || DEFAULT_WORKSPACE_ROOT;
      console.debug("Client sandbox workspace root", workspaceRoot);
      await enableClientSandboxPreference({ deviceId, workspaceRoot });
      await startClientSandboxService();
      setIsEnabled(true);
      toast.success(t("chat.clientSandbox.enabled"));
    } catch (error) {
      console.error("Failed to enable client sandbox", error);
      toast.error(t("chat.clientSandbox.enableFailed"));
    } finally {
      setIsEnabling(false);
    }
  }, [isEnabling, t]);

  if (!isDesktopSandboxAvailable) return null;

  const disabled = isEnabling;
  const title = isEnabled
    ? t("chat.clientSandbox.enabled")
    : t("chat.clientSandbox.enable");

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        void handleEnable();
      }}
      className="flex items-center justify-center rounded-full p-2 transition-all duration-300 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
      style={
        isEnabled
          ? {
              border: "1px solid color-mix(in srgb, #22c55e 45%, transparent)",
              background: "color-mix(in srgb, #22c55e 12%, transparent)",
              color: "#16a34a",
            }
          : {
              backgroundColor: "transparent",
              border: "1px solid var(--theme-border)",
              color: "var(--theme-text-secondary)",
            }
      }
      title={title}
      aria-label={title}
    >
      {isEnabling ? (
        <Loader2 size={18} className="animate-spin" />
      ) : (
        <Monitor size={18} />
      )}
    </button>
  );
}
