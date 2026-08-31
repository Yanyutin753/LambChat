import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { AlertCircle, DraftingCompass } from "lucide-react";
import { DxfViewer } from "dxf-viewer";
import type { TFunction } from "i18next";
import FileFallbackPanel from "./FileFallbackPanel";
import "./CadPreview.css";

type CadKind = "dxf" | "dwg";
type LoadPhase = "font" | "fetch" | "parse" | "prepare";

interface CadPreviewProps {
  fileName: string;
  kind: CadKind;
  url?: string | null;
  t: TFunction;
}

function formatPhase(phase: LoadPhase | null, t: TFunction): string {
  if (!phase) return t("documents.cadPreparing", "Preparing CAD preview");
  const phaseLabels: Record<LoadPhase, string> = {
    font: t("documents.cadLoadingFonts", "Loading CAD fonts"),
    fetch: t("documents.cadFetching", "Loading CAD file"),
    parse: t("documents.cadParsing", "Parsing drawing"),
    prepare: t("documents.cadRendering", "Preparing geometry"),
  };
  return phaseLabels[phase];
}

export default function CadPreview(props: CadPreviewProps) {
  const { kind, url, t } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [phase, setPhase] = useState<LoadPhase | null>(null);
  const [progress, setProgress] = useState(0);

  const progressPercent = useMemo(() => {
    if (progress > 0) return Math.min(100, Math.max(8, progress));
    if (phase === "prepare") return 90;
    if (phase === "parse") return 70;
    if (phase === "fetch") return 35;
    return 16;
  }, [phase, progress]);

  useEffect(() => {
    if (kind !== "dxf" || !url || !containerRef.current) return;

    let cancelled = false;
    const viewer = new DxfViewer(containerRef.current, {
      autoResize: true,
      antialias: true,
      clearAlpha: 0,
      canvasAlpha: true,
      colorCorrection: true,
      blackWhiteInversion: true,
    });

    if (!viewer.HasRenderer()) {
      setError(t("documents.cadWebglUnavailable", "WebGL is not available"));
      return () => viewer.Destroy();
    }

    setError(null);
    setLoaded(false);
    setPhase(null);
    setProgress(0);

    viewer
      .Load({
        url,
        progressCbk: (nextPhase, processedSize, totalSize) => {
          if (cancelled) return;
          setPhase(nextPhase);
          if (totalSize && totalSize > 0) {
            setProgress((processedSize / totalSize) * 100);
          }
        },
      })
      .then(() => {
        if (!cancelled) {
          setLoaded(true);
          setProgress(100);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          console.error("Failed to render DXF:", err);
          setError(
            t("documents.cadPreviewFailed", "Failed to render CAD file"),
          );
        }
      });

    return () => {
      cancelled = true;
      viewer.Destroy();
    };
  }, [kind, t, url]);

  if (kind === "dwg") {
    return (
      <FileFallbackPanel
        icon={DraftingCompass}
        iconBg="bg-slate-100 dark:bg-slate-800"
        title={t(
          "documents.dwgPreviewUnsupported",
          "DWG preview is not supported",
        )}
        description={t(
          "documents.dwgPreviewHint",
          "Please download this file or convert it to DXF/PDF for browser preview.",
        )}
        downloadUrl={url}
        fileName={props.fileName}
        downloadLabel={t("documents.download", "Download")}
      />
    );
  }

  return (
    <div className="cad-preview">
      <div ref={containerRef} className="cad-preview__viewer" />
      {(!loaded || error) && (
        <div className="cad-preview__overlay">
          <div className="cad-preview__panel">
            {error ? (
              <>
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-100 dark:bg-red-900/30">
                  <AlertCircle size={30} className="text-red-500" />
                </div>
                <h3 className="mb-2 text-base font-medium font-serif text-[var(--theme-text)]">
                  {error}
                </h3>
                <p className="text-sm text-[var(--theme-text-secondary)]">
                  {t(
                    "documents.cadPreviewFallbackHint",
                    "This DXF may use unsupported entities. You can still download the original file.",
                  )}
                </p>
              </>
            ) : (
              <>
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-100 dark:bg-cyan-900/40">
                  <DraftingCompass
                    size={30}
                    className="text-cyan-700 dark:text-cyan-300"
                  />
                </div>
                <h3 className="mb-4 text-base font-medium font-serif text-[var(--theme-text)]">
                  {formatPhase(phase, t)}
                </h3>
                <div
                  className="cad-preview__progress"
                  style={
                    {
                      "--cad-progress": `${progressPercent}%`,
                    } as CSSProperties
                  }
                >
                  <div className="cad-preview__progress-bar" />
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
