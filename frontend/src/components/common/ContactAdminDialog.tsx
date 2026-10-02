import { Mail, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api/auth";
import { Dialog } from "./Dialog";
import { SceneIllustration } from "./SceneIllustration";
import { LoadingSpinner } from "./LoadingSpinner";
import { Button } from "./ui/Button";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

interface ContactAdminDialogProps {
  isOpen: boolean;
  onClose: () => void;
  reason?: "noPermission" | "emailActivation";
}

export function ContactAdminDialog({
  isOpen,
  onClose,
  reason = "noPermission",
}: ContactAdminDialogProps) {
  const { t } = useTranslation();
  const [result, setResult] = useState<{
    email?: string;
    url?: string;
    error?: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setResult(null);
    if (!isOpen) return;
    const controller = new AbortController();
    authApi.getOAuthProviders(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setResult(
            data
              ? (data.admin_contact ?? {})
              : { error: t("settings.loadFailed") },
          );
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            error:
              error instanceof Error ? error.message : t("settings.loadFailed"),
          });
      },
    );
    return () => controller.abort();
  }, [isOpen, attempt, t]);
  const isLoading = result === null;
  const adminEmail = result?.email;
  const adminUrl = result?.url;
  const error = result?.error;
  const title = t(
    reason === "emailActivation"
      ? "contactAdmin.emailActivationTitle"
      : "contactAdmin.noPermissionTitle",
  );
  const description = t(
    reason === "emailActivation"
      ? "contactAdmin.emailActivationDesc"
      : "contactAdmin.noPermissionDesc",
  );
  const linkClass =
    "flex min-h-11 min-w-0 items-center gap-3 rounded-lg px-3 py-3 text-14 text-theme-text transition-colors hover:bg-theme-bg-subtle focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]";

  return (
    <Dialog
      open={isOpen}
      onClose={onClose}
      size="sm"
      title={
        <span className="text-16 font-semibold font-serif tracking-tight">
          {title}
        </span>
      }
    >
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <SceneIllustration scene="message" className="!h-16 !w-16 shrink-0" />
          <p className="min-w-0 text-14 leading-relaxed text-theme-text-secondary">
            {description}
          </p>
        </div>
        {isLoading ? (
          <div
            role="status"
            className="flex min-h-11 items-center gap-2 text-14 text-theme-text-secondary"
          >
            <LoadingSpinner size="sm" />
            {t("common.loading")}
          </div>
        ) : error ? (
          <div className="space-y-3">
            <ConfigPanelErrorCallout message={error} />
            <Button
              className="!min-h-11 sm:!min-h-9 [@media(pointer:coarse)]:!min-h-11"
              onClick={(event) => {
                event.currentTarget
                  .closest<HTMLElement>("[data-modal-surface]")
                  ?.focus();
                setAttempt((value) => value + 1);
              }}
            >
              {t("common.retry")}
            </Button>
          </div>
        ) : adminEmail || adminUrl ? (
          <div className="space-y-1">
            {adminEmail && (
              <a href={`mailto:${adminEmail}`} className={linkClass}>
                <Mail
                  size={16}
                  className="shrink-0 text-theme-text-tertiary"
                  aria-hidden="true"
                />
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  {adminEmail}
                </span>
              </a>
            )}
            {adminUrl && (
              <a
                href={adminUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={linkClass}
              >
                <ExternalLink
                  size={16}
                  className="shrink-0 text-theme-text-tertiary"
                  aria-hidden="true"
                />
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  {t("contactAdmin.supportLink")}
                </span>
              </a>
            )}
          </div>
        ) : (
          <p className="text-14 leading-relaxed text-theme-text-secondary">
            {t("contactAdmin.noContactInfo")}
          </p>
        )}
      </div>
    </Dialog>
  );
}
