import { SceneIllustration } from "../../common/SceneIllustration";
import { type ElementType } from "react";
import { Download } from "lucide-react";
import { Button } from "../../common/ui/Button";
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
          <SceneIllustration scene="files" className="mx-auto mb-3" />
          <div
            className={`mx-auto mb-3 flex size-8 items-center justify-center rounded-lg ${iconBg}`}
          >
            <Icon size={18} className={iconColor} />
          </div>
          <h3 className="mb-2 text-16 font-medium font-serif text-[var(--theme-text)]">
            {title}
          </h3>
          <p className="mb-5 text-14 text-[var(--theme-text-secondary)]">
            {description}
          </p>
          {(downloadUrl || onDownload) && (
            <Button
              size="lg"
              onClick={handleDownload}
              leftIcon={<Download size={16} aria-hidden="true" />}
            >
              {downloadLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
