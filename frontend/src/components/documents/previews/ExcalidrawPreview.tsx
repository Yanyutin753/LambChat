import {
  memo,
  useEffect,
  useState,
  useRef,
  useCallback,
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

interface ExcalidrawPreviewProps {
  data: string; // JSON string of excalidraw file content
}

interface ExcalidrawAPI {
  updateScene: (scene: {
    elements: readonly ExcalidrawElement[];
    appState?: ExcalidrawAppState;
  }) => void;
  scrollToContent: (
    elements?: readonly ExcalidrawElement[],
    opts?: { fitToViewport?: boolean; animate?: boolean },
  ) => void;
}

interface ExcalidrawComponentProps {
  excalidrawAPI?: (api: ExcalidrawAPI) => void;
  initialData?: ExcalidrawInitialData;
  viewModeEnabled?: boolean;
  zenModeEnabled?: boolean;
  gridModeEnabled?: boolean;
}

type ExcalidrawComponent = ComponentType<ExcalidrawComponentProps>;

// Cache the loaded module globally
let ExcalidrawModuleCache: ExcalidrawComponent | null = null;

const ExcalidrawPreview = memo(function ExcalidrawPreview({
  data,
}: ExcalidrawPreviewProps) {
  const [Excalidraw, setExcalidraw] = useState<ExcalidrawComponent | null>(
    ExcalidrawModuleCache,
  );
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(!ExcalidrawModuleCache);

  const excalidrawAPIRef = useRef<ExcalidrawAPI | null>(null);
  const lastDataRef = useRef<string>("");
  const isInitialMount = useRef(true);
  const parsedDataRef = useRef<ExcalidrawInitialData | null>(null);

  // Load Excalidraw module once
  useEffect(() => {
    if (ExcalidrawModuleCache) {
      return;
    }

    setIsLoading(true);
    import("@excalidraw/excalidraw")
      .then((mod) => {
        const ExcalidrawFromModule = (
          mod as unknown as { Excalidraw: ExcalidrawComponent }
        ).Excalidraw;
        ExcalidrawModuleCache = ExcalidrawFromModule;
        setExcalidraw(() => ExcalidrawFromModule);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load Excalidraw:", err);
        setError("Failed to load Excalidraw library");
        setIsLoading(false);
      });
  }, []);

  // Parse and update data
  const parseAndUpdateData = useCallback((rawData: string) => {
    if (!rawData) return null;

    try {
      const parsed = JSON.parse(rawData);
      const elements = parsed.elements || parsed;
      const appState = parsed.appState || {};

      if (!Array.isArray(elements)) {
        console.error("Invalid excalidraw file: elements is not an array");
        setError("Invalid Excalidraw file format");
        return null;
      }

      return {
        elements: elements as ExcalidrawElement[],
        appState: {
          ...appState,
          viewBackgroundColor: appState.viewBackgroundColor || "#ffffff",
        },
      };
    } catch (e) {
      console.error("Failed to parse excalidraw file:", e);
      setError("Failed to parse Excalidraw file");
      return null;
    }
  }, []);

  // Handle data changes
  useEffect(() => {
    if (!data || data === lastDataRef.current) {
      return;
    }
    lastDataRef.current = data;

    const parsed = parseAndUpdateData(data);
    if (!parsed) {
      return;
    }

    parsedDataRef.current = parsed;
    setError(null);

    // If API is already available, update the scene immediately
    if (excalidrawAPIRef.current) {
      excalidrawAPIRef.current.updateScene({
        elements: parsed.elements,
        appState: parsed.appState,
      });
      excalidrawAPIRef.current.scrollToContent(
        parsed.elements as ExcalidrawElement[],
        { fitToViewport: true, animate: false },
      );
    }
  }, [data, parseAndUpdateData]);

  // Handle API ready
  const handleAPIReady = useCallback((api: ExcalidrawAPI) => {
    excalidrawAPIRef.current = api;

    // If we already have data, apply it now
    if (parsedDataRef.current && isInitialMount.current) {
      isInitialMount.current = false;
      api.updateScene({
        elements: parsedDataRef.current.elements,
        appState: parsedDataRef.current.appState,
      });
      api.scrollToContent(
        parsedDataRef.current.elements as ExcalidrawElement[],
        {
          fitToViewport: true,
          animate: false,
        },
      );
    }
  }, []);

  // Error state
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

  // Loading state
  if (isLoading || !Excalidraw) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <LoadingSpinner size="lg" />
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {isLoading ? "Loading Excalidraw library..." : "Loading drawing..."}
        </p>
      </div>
    );
  }

  // Parse initial data for first render
  const initialData = parsedDataRef.current || parseAndUpdateData(data);

  // Render the Excalidraw component
  const ExcalidrawComponent = Excalidraw;

  return (
    <div
      className="excalidraw-preview-container"
      style={{
        height: "100%",
        width: "100%",
        maxHeight: "100%",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <ExcalidrawComponent
        excalidrawAPI={handleAPIReady}
        initialData={initialData ?? undefined}
        viewModeEnabled={true}
        zenModeEnabled={false}
        gridModeEnabled={false}
      />
    </div>
  );
});

export default ExcalidrawPreview;
