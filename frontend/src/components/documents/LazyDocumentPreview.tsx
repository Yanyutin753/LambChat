import { Suspense, lazy } from "react";
import type { ComponentProps } from "react";
import { useTranslation } from "react-i18next";
import { Loading } from "../common/LoadingSpinner";
import type DocumentPreview from "./DocumentPreview";

const DocumentPreviewContent = lazy(() => import("./DocumentPreview"));

type LazyDocumentPreviewProps = ComponentProps<typeof DocumentPreview>;

function DocumentPreviewFallback() {
  const { t } = useTranslation();
  return (
    <div className="safe-area-viewport-padding fixed inset-0 z-[90] flex items-center justify-center bg-black/50">
      <div className="rounded-2xl bg-white/90 px-4 py-3 shadow-xl dark:bg-stone-900/90">
        <Loading text={t("project.loadingPreview")} />
      </div>
    </div>
  );
}

export function LazyDocumentPreview(props: LazyDocumentPreviewProps) {
  return (
    <Suspense
      fallback={props.embedded ? <Loading /> : <DocumentPreviewFallback />}
    >
      <DocumentPreviewContent {...props} />
    </Suspense>
  );
}
