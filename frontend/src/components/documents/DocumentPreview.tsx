import { ToolResultPanel } from "../chat/ChatMessage/items/ToolResultPanel";
import DocumentPreviewToolbar from "./DocumentPreviewToolbar";
import DocumentPreviewContent from "./DocumentPreviewContent";
import {
  useDocumentPreviewState,
  type DocumentPreviewProps,
} from "./useDocumentPreviewState";

export type { DocumentPreviewProps };

export default function DocumentPreview(props: DocumentPreviewProps) {
  const state = useDocumentPreviewState(props);

  return (
    <ToolResultPanel
      open={true}
      automatic={state.automatic}
      onClose={state.onClose}
      registryKey={state.registryKey}
      viewMode={state.isMobile ? "center" : state.viewMode}
      isFullscreen={state.isFullscreen}
      panelElementRef={state.panelRef}
      mobileFillViewport={state.mobileFillViewport}
      onUserInteraction={state.onUserInteraction}
      onBack={state.effectiveOnBack}
      footer={
        <div className="px-3 sm:px-5 py-2 sm:py-3 border-t border-[var(--theme-border)] bg-[var(--theme-primary-light)]">
          <div className="flex items-center justify-between text-xs sm:text-xs text-[var(--theme-text-secondary)]">
            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 flex-1">
              <span className="font-medium text-[var(--theme-text-secondary)] hidden xs:inline">
                {state.t("documents.path")}:
              </span>
              <span className="font-serif text-[var(--theme-text)] truncate text-xs sm:text-xs">
                {state.path}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0 ml-2 font-serif">
              {state.footer}
              <span className="hidden sm:inline">
                {state.t("documents.pressEscToClose")}
              </span>
            </div>
          </div>
        </div>
      }
      customHeader={<DocumentPreviewToolbar {...state} />}
    >
      <DocumentPreviewContent {...state} />
    </ToolResultPanel>
  );
}
