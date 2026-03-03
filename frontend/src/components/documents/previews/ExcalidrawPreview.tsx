import {
  memo,
  useEffect,
  useState,
  useCallback,
  Suspense,
  lazy,
  ComponentType,
} from "react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { AlertCircle } from "lucide-react";

// Types for Excalidraw API - using minimal interface
interface ExcalidrawAPI {
  updateScene: (scene: { elements: unknown[]; appState?: unknown }) => void;
  getSceneElements: () => unknown[];
}

interface ExcalidrawPreviewProps {
  data: string; // JSON string of excalidraw file content
}

// Props interface for the Excalidraw component
interface ExcalidrawComponentProps {
  excalidrawAPI: (api: ExcalidrawAPI) => void;
  viewModeEnabled: boolean;
}

// Lazy load Excalidraw component using React.lazy
// Use type assertion via unknown to bypass strict type checking from the excalidraw library
const ExcalidrawComponent = lazy(() =>
  import("@excalidraw/excalidraw").then((mod) => ({
    default: (
      mod as unknown as { Excalidraw: ComponentType<ExcalidrawComponentProps> }
    ).Excalidraw,
  })),
);

const ExcalidrawPreview = memo(function ExcalidrawPreview({
  data,
}: ExcalidrawPreviewProps) {
  const [excalidrawAPI, setExcalidrawAPI] = useState<ExcalidrawAPI | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Parse and load excalidraw data
  useEffect(() => {
    if (!excalidrawAPI || !data) return;

    try {
      const parsed = JSON.parse(data);

      // Handle both old and new excalidraw formats
      const elements = parsed.elements || parsed;
      const appState = parsed.appState || {};

      if (Array.isArray(elements)) {
        excalidrawAPI.updateScene({
          elements,
          appState: {
            ...appState,
            viewBackgroundColor: appState.viewBackgroundColor || "#ffffff",
          },
        });
        setLoading(false);
      } else {
        console.error("Invalid excalidraw file: elements is not an array");
        setError("Invalid Excalidraw file format");
        setLoading(false);
      }
    } catch (e) {
      console.error("Failed to parse excalidraw file:", e);
      setError("Failed to parse Excalidraw file");
      setLoading(false);
    }
  }, [excalidrawAPI, data]);

  const handleAPIReady = useCallback((api: ExcalidrawAPI) => {
    setExcalidrawAPI(api);
  }, []);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
        <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-red-100 dark:bg-red-900/30">
          <AlertCircle size={28} className="text-red-500" />
        </div>
        <div className="text-center">
          <p className="text-sm text-red-600 dark:text-red-400 font-medium mb-2">
            {error}
          </p>
          <p className="text-xs text-stone-400 dark:text-stone-500">
            The file may be corrupted or in an unsupported format.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full relative">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white dark:bg-stone-900 z-10">
          <div className="flex flex-col items-center gap-4">
            <LoadingSpinner size="lg" />
            <p className="text-sm text-stone-500 dark:text-stone-400">
              Loading Excalidraw...
            </p>
          </div>
        </div>
      )}
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-full">
            <LoadingSpinner size="lg" />
          </div>
        }
      >
        <ExcalidrawComponent
          excalidrawAPI={handleAPIReady}
          viewModeEnabled={true}
        />
      </Suspense>
    </div>
  );
});

export default ExcalidrawPreview;
