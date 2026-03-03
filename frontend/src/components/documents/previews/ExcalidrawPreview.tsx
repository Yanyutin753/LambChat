import {
  memo,
  useEffect,
  useState,
  Suspense,
  lazy,
  ComponentType,
} from "react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { AlertCircle } from "lucide-react";

// Types for Excalidraw
interface ExcalidrawElement {
  id: string;
  [key: string]: unknown;
}

interface ExcalidrawAppState {
  viewBackgroundColor?: string;
  [key: string]: unknown;
}

interface ExcalidrawInitialData {
  elements: readonly ExcalidrawElement[];
  appState?: ExcalidrawAppState;
}

interface ExcalidrawComponentProps {
  initialData?: ExcalidrawInitialData | null;
  viewModeEnabled?: boolean;
  zenModeEnabled?: boolean;
  gridModeEnabled?: boolean;
}

interface ExcalidrawPreviewProps {
  data: string; // JSON string of excalidraw file content
}

// Lazy load Excalidraw component
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
  const [initialData, setInitialData] = useState<ExcalidrawInitialData | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Parse excalidraw data on mount
  useEffect(() => {
    if (!data) {
      setLoading(false);
      return;
    }

    try {
      const parsed = JSON.parse(data);

      // Handle both old and new excalidraw formats
      const elements = parsed.elements || parsed;
      const appState = parsed.appState || {};

      if (Array.isArray(elements)) {
        setInitialData({
          elements: elements as ExcalidrawElement[],
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
  }, [data]);

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

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <LoadingSpinner size="lg" />
        <p className="text-sm text-stone-500 dark:text-stone-400">
          Loading Excalidraw...
        </p>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <Suspense
        fallback={
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <LoadingSpinner size="lg" />
            <p className="text-sm text-stone-500 dark:text-stone-400">
              Loading Excalidraw library...
            </p>
          </div>
        }
      >
        <ExcalidrawComponent
          initialData={initialData}
          viewModeEnabled={true}
          zenModeEnabled={false}
          gridModeEnabled={false}
        />
      </Suspense>
    </div>
  );
});

export default ExcalidrawPreview;
