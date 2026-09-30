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
      title={state.path.split("/").pop() || state.path}
      icon={<state.Icon size={14} />}
      automatic={state.automatic}
      onClose={state.onClose}
      registryKey={state.registryKey}
      viewMode={state.viewMode}
      onViewModeChange={state.setViewMode}
      isFullscreen={state.isFullscreen}
      panelElementRef={state.panelRef}
      mobileFillViewport={state.mobileFillViewport}
      onUserInteraction={state.onUserInteraction}
      onBack={state.effectiveOnBack}
      footer={
        (state.footer || state.path.includes("/")) && (
          <div className="document-preview-footer">
            {state.path.includes("/") && (
              <details className="document-preview-path">
                <summary>{state.t("documents.path")}</summary>
                <div>{state.path}</div>
              </details>
            )}
            {state.footer}
          </div>
        )
      }
      customHeader={<DocumentPreviewToolbar {...state} />}
    >
      <DocumentPreviewContent {...state} />
    </ToolResultPanel>
  );
}
