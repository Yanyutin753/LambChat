import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type Ref,
} from "react";
import { ViewerToolbar } from "../../common/ViewerToolbar";
import { LoadingSpinner } from "../../common/LoadingSpinner";

const DEFAULT_MIN_ZOOM = 0.5;
const DEFAULT_MAX_ZOOM = 3;
const DEFAULT_ZOOM_STEP = 0.2;
const DOCUMENT_HORIZONTAL_PADDING = 40;

export interface DocumentViewerLayout {
  zoom: number;
  fitScale: number;
  displayScale: number;
}

interface DocumentViewerFrameProps {
  naturalWidth: number;
  loading?: boolean;
  ariaLabel?: string;
  minZoom?: number;
  maxZoom?: number;
  zoomStep?: number;
  children: (layout: DocumentViewerLayout) => ReactNode;
}

interface ScaledDocumentContentProps {
  naturalWidth: number;
  naturalHeight: number;
  displayScale: number;
  contentRef?: Ref<HTMLDivElement>;
  className?: string;
  children?: ReactNode;
}

export function calculateDocumentFitScale(
  viewportWidth: number,
  naturalWidth: number,
  horizontalPadding = DOCUMENT_HORIZONTAL_PADDING,
): number {
  if (viewportWidth <= 0 || naturalWidth <= 0) return 1;
  return Math.min(
    1,
    Math.max(0.1, (viewportWidth - horizontalPadding) / naturalWidth),
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function ScaledDocumentContent({
  naturalWidth,
  naturalHeight,
  displayScale,
  contentRef,
  className,
  children,
}: ScaledDocumentContentProps) {
  return (
    <div
      data-testid="scaled-document-bounds"
      className="relative shrink-0"
      style={{
        width: naturalWidth * displayScale,
        height: naturalHeight * displayScale,
      }}
    >
      <div
        ref={contentRef}
        data-testid="scaled-document-content"
        className={className}
        style={{
          width: naturalWidth,
          height: naturalHeight,
          transform: `scale(${displayScale})`,
          transformOrigin: "top left",
        }}
      >
        {children}
      </div>
    </div>
  );
}

export function DocumentViewerFrame({
  naturalWidth,
  loading = false,
  ariaLabel,
  minZoom = DEFAULT_MIN_ZOOM,
  maxZoom = DEFAULT_MAX_ZOOM,
  zoomStep = DEFAULT_ZOOM_STEP,
  children,
}: DocumentViewerFrameProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const updateWidth = () => setViewportWidth(viewport.clientWidth);
    updateWidth();

    const observer = new ResizeObserver(updateWidth);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  const fitScale = useMemo(
    () => calculateDocumentFitScale(viewportWidth, naturalWidth),
    [naturalWidth, viewportWidth],
  );
  const displayScale = fitScale * zoom;

  const zoomIn = useCallback(() => {
    setZoom((current) =>
      Number(clamp(current + zoomStep, minZoom, maxZoom).toFixed(2)),
    );
  }, [maxZoom, minZoom, zoomStep]);

  const zoomOut = useCallback(() => {
    setZoom((current) =>
      Number(clamp(current - zoomStep, minZoom, maxZoom).toFixed(2)),
    );
  }, [maxZoom, minZoom, zoomStep]);

  const resetView = useCallback(() => setZoom(1), []);

  return (
    <div className="relative h-full min-h-[400px] w-full overflow-hidden bg-stone-200 dark:bg-stone-950">
      <div
        ref={viewportRef}
        aria-label={ariaLabel}
        className="h-full min-h-0 w-full overflow-auto"
      >
        <div className="box-border flex min-h-full min-w-full w-max items-start justify-center px-3 py-4 pb-24 sm:px-5 sm:py-5 sm:pb-28">
          {children({ zoom, fitScale, displayScale })}
        </div>
      </div>

      {loading && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-stone-100/80 dark:bg-stone-950/80">
          <LoadingSpinner
            className="text-stone-400 dark:text-stone-500"
            size="lg"
          />
        </div>
      )}

      {!loading && (
        <ViewerToolbar
          scale={zoom}
          minScale={minZoom}
          maxScale={maxZoom}
          showRotation={false}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onRotateLeft={() => {}}
          onRotateRight={() => {}}
          onReset={resetView}
        />
      )}
    </div>
  );
}
