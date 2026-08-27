import { type ElementType } from "react";
import { Download } from "lucide-react";
import type { TFunction } from "i18next";
import "./FileFallbackPanel.css";

interface FileFallbackPanelProps {
  icon: ElementType;
  iconBg: string;
  iconColor?: string;
  title: string;
  description: string;
  downloadUrl?: string | null;
  fileName: string;
  downloadLabel: string;
  t?: TFunction;
  onDownload?: () => void;
}

export default function FileFallbackPanel({
  icon: Icon,
  iconBg,
  iconColor = "text-slate-600 dark:text-slate-300",
  title,
  description,
  downloadUrl,
  fileName,
  downloadLabel,
  onDownload,
}: FileFallbackPanelProps) {
  const handleDownload = () => {
    if (onDownload) {
      onDownload();
      return;
    }
    if (!downloadUrl) return;
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="unsupported-file-fallback">
      <div className="unsupported-file-fallback__overlay">
        <div className="unsupported-file-fallback__panel">
          <div
            className={`mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl ${iconBg}`}
          >
            <Icon size={30} className={iconColor} />
          </div>
          <h3 className="mb-2 text-base font-medium font-serif text-[var(--theme-text)]">
            {title}
          </h3>
          <p className="mb-5 text-sm text-[var(--theme-text-secondary)]">
            {description}
          </p>
          {(downloadUrl || onDownload) && (
            <button
              type="button"
              onClick={handleDownload}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 dark:bg-slate-600 dark:hover:bg-slate-500"
            >
              <Download size={16} />
              {downloadLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
