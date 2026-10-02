import { useTranslation } from "react-i18next";

interface UpdateProgressBarProps {
  progress: number;
  downloaded: number;
  contentLength: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UpdateProgressBar({
  progress,
  downloaded,
  contentLength,
}: UpdateProgressBarProps) {
  const { t } = useTranslation();

  const percent = Number.isFinite(progress)
    ? Math.max(0, Math.min(Math.round(progress), 100))
    : 0;
  const downloadedStr = formatBytes(downloaded);
  const totalStr = contentLength > 0 ? formatBytes(contentLength) : "?";

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-12 text-theme-text-secondary">
        <span>{t("updateDownloading", "正在下载...")}</span>
        <span>
          {downloadedStr} / {totalStr} — {percent}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={t("updateDownloading", "正在下载...")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 w-full overflow-hidden rounded-full bg-theme-border"
      >
        <div
          className="h-full rounded-full bg-[var(--theme-primary)] transition-[width] duration-300 ease-out motion-reduce:transition-none"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
