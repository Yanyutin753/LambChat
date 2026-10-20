import { Suspense, lazy } from "react";
import { useTranslation } from "react-i18next";

import type { CodeMirrorViewerProps } from "./CodeMirrorViewer";
import { LoadingSpinner } from "./LoadingSpinner";

const LazyCodeMirrorViewer = lazy(() =>
  import("./CodeMirrorViewer").then((module) => ({
    default: module.CodeMirrorViewer,
  })),
);

function CodeMirrorFallback({
  className,
  maxHeight,
  fontSize,
}: Pick<CodeMirrorViewerProps, "className" | "maxHeight" | "fontSize">) {
  const { t } = useTranslation();
  const loadingLabel = t("common.loading");

  return (
    <div className={className}>
      <div
        aria-label={loadingLabel}
        role="status"
        className="flex min-h-24 items-center justify-center bg-theme-bg-code p-3 text-theme-text-tertiary"
        style={{
          ...(maxHeight ? { maxHeight } : {}),
          ...(fontSize ? { fontSize } : {}),
        }}
      >
        <LoadingSpinner size="sm" color="text-current" />
      </div>
    </div>
  );
}

export function DeferredCodeMirrorViewer(props: CodeMirrorViewerProps) {
  return (
    <Suspense
      fallback={
        <CodeMirrorFallback
          className={props.className}
          maxHeight={props.maxHeight}
          fontSize={props.fontSize}
        />
      }
    >
      <LazyCodeMirrorViewer {...props} />
    </Suspense>
  );
}
