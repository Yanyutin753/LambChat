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
  const parentSegments = state.path.split("/").filter(Boolean).slice(0, -1);

  if (props.embedded) {
    return (
      <div ref={state.panelRef} className="workspace-document">
        <DocumentPreviewToolbar {...state} embedded />
        {parentSegments.length > 0 && (
          <div
            className="workspace-document-breadcrumb"
            title={state.path}
            aria-label={state.t("documents.path")}
          >
            {parentSegments.map((segment, index) => (
              <span key={index}>
                {index > 0 && <span aria-hidden="true"> / </span>}
                {segment}
              </span>
            ))}
          </div>
        )}
        <div className="workspace-document-content">
          <DocumentPreviewContent {...state} />
        </div>
        <div className="workspace-document-status">
          {state.footer}
          <span>{state.language || state.t(state.fileInfo.label)}</span>
        </div>
      </div>
    );
  }

  return (
    <ToolResultPanel
      open={true}
      title={state.path.split("/").pop() || state.path}
      icon={<state.Icon size={14} />}
      path={state.path}
      fileType={state.t(state.fileInfo.label)}
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
