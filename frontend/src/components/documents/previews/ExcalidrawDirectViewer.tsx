import { useEffect, useState } from "react";
import { buildUploadProxyUrl, getFullUrl } from "../../../services/api/config";
import { fetchDocumentText } from "../documentFetchCache";
import { ExcalidrawFullscreenViewer } from "./ExcalidrawPreview";
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
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const fullUrl = getFullUrl(url) ?? url;
    const readUrl = buildUploadProxyUrl(url) ?? fullUrl;
    let cancelled = false;
    setSvgContent(null);
    setError(false);

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
  }, [url, attempt]);

  return (
    <ExcalidrawFullscreenViewer
      svgContent={svgContent}
      onClose={onClose}
      loading={!svgContent && !error}
      error={error ? t("documents.excalidrawRenderFailed") : undefined}
      onRetry={() => setAttempt((current) => current + 1)}
    />
  );
}
