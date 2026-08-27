import { useEffect, useState } from "react";
import { buildUploadProxyUrl, getFullUrl } from "../../../services/api/config";
import { fetchDocumentText } from "../documentFetchCache";
import { ExcalidrawFullscreenViewer } from "./ExcalidrawPreview";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { useTranslation } from "react-i18next";

/**
 * Direct fullscreen viewer for excalidraw files — fetches JSON from a URL,
 * exports to SVG, and opens the dark fullscreen viewer (matching ImageViewer pattern).
 * Used by RevealedFilesPanel for click-to-preview on file cards.
 */
export function ExcalidrawDirectViewer({
  url,
  onClose,
}: {
  url: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fullUrl = getFullUrl(url) ?? url;
    const readUrl = buildUploadProxyUrl(url) ?? fullUrl;
    let cancelled = false;

    const load = async () => {
      try {
        const data = await fetchDocumentText(readUrl);
        if (cancelled) return;

        // Parse excalidraw JSON
        const parsed = JSON.parse(data);
        const elements = parsed.elements || parsed;
        if (!Array.isArray(elements)) throw new Error("Invalid excalidraw");

        // Lazy-load exportToSvg
        const { exportToSvg } = await import("@excalidraw/excalidraw");
        if (cancelled) return;

        const svg = await exportToSvg({
          elements,
          appState: {
            ...(parsed.appState || {}),
            exportWithDarkMode: false,
          },
        });

        const svgString = new XMLSerializer().serializeToString(svg);
        if (!cancelled) setSvgContent(svgString);
      } catch {
        if (!cancelled) setError(true);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (error) {
    return (
      <div className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center bg-black/90">
        <div className="flex flex-col items-center gap-3">
          <p className="text-sm text-white/70">
            {t("documents.excalidrawRenderFailed", "Failed to render diagram")}
          </p>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-white/70 hover:bg-white/10 transition-colors"
          >
            {t("common.close", "Close")}
          </button>
        </div>
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center bg-black/90">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <ExcalidrawFullscreenViewer svgContent={svgContent} onClose={onClose} />
  );
}
