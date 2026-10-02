import { RefreshCw, ExternalLink, ArrowDownCircle, Github } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useVersion } from "../../hooks/useVersion";
import { APP_NAME } from "../../constants";
import { APP_VERSION } from "../../utils/appVersion";
import { Dialog } from "./Dialog";
import { Button } from "./ui/Button";
import { LoadingSpinner } from "./LoadingSpinner";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

interface AboutDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AboutDialog({ isOpen, onClose }: AboutDialogProps) {
  const { t } = useTranslation();
  const { versionInfo, isLoading, error, checkForUpdates } = useVersion();
  const actionClass =
    "max-w-full !min-h-11 sm:!min-h-9 [@media(pointer:coarse)]:!min-h-11 [&>span]:!whitespace-normal";
  const linkClass = `ui-button ui-button--secondary ui-button--md w-full ${actionClass}`;

  return (
    <Dialog
      open={isOpen}
      onClose={onClose}
      size="md"
      title={
        <span className="font-serif tracking-tight">
          {t("about.title", APP_NAME)}
        </span>
      }
      footer={
        <Button
          variant="primary"
          className={`w-full sm:w-auto ${actionClass}`}
          loading={isLoading}
          aria-busy={isLoading}
          leftIcon={<RefreshCw size={16} aria-hidden="true" />}
          onClick={(event) => {
            event.currentTarget
              .closest<HTMLElement>("[data-modal-surface]")
              ?.focus();
            void checkForUpdates();
          }}
        >
          {t(error ? "common.retry" : "about.checkUpdate")}
        </Button>
      }
    >
      <div className="space-y-4">
        <dl className="space-y-3">
          <div>
            <dt className="text-12 text-theme-text-secondary">
              {t("about.currentVersion")}
            </dt>
            <dd className="mt-1 font-mono text-24 font-semibold text-theme-text [overflow-wrap:anywhere]">
              {APP_VERSION}
            </dd>
          </div>
          {versionInfo?.latest_version && (
            <div>
              <dt className="text-12 text-theme-text-secondary">
                {t("about.latestVersion")}
              </dt>
              <dd className="mt-1 font-mono text-16 text-theme-text [overflow-wrap:anywhere]">
                {versionInfo.latest_version}
              </dd>
            </div>
          )}
        </dl>
        {isLoading && (
          <div
            role="status"
            className="flex items-center gap-2 text-14 text-theme-text-secondary"
          >
            <LoadingSpinner size="sm" />
            {t("common.loading")}
          </div>
        )}
        {error && <ConfigPanelErrorCallout message={error} />}
        {versionInfo?.latest_version && (
          <p className="flex items-start gap-2 text-14 text-theme-text-secondary">
            <ArrowDownCircle
              size={16}
              className="mt-0.5 shrink-0"
              aria-hidden="true"
            />
            {t(
              versionInfo.has_update
                ? "about.updateAvailable"
                : "about.upToDate",
            )}
          </p>
        )}
        {versionInfo?.has_update && versionInfo.release_url && (
          <a
            href={versionInfo.release_url}
            target="_blank"
            rel="noopener noreferrer"
            className={linkClass}
          >
            <ExternalLink size={16} className="shrink-0" aria-hidden="true" />
            <span className="ui-button__label">{t("about.viewUpdate")}</span>
          </a>
        )}
        {versionInfo?.github_url && (
          <a
            href={versionInfo.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className={linkClass}
          >
            <Github size={16} className="shrink-0" aria-hidden="true" />
            <span className="ui-button__label">{t("about.viewOnGitHub")}</span>
          </a>
        )}
      </div>
    </Dialog>
  );
}
