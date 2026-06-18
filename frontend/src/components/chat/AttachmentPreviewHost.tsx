import { useEffect, useRef, useState } from "react";
import { DelayedUnmount } from "../common/DelayedUnmount";
import { getFullUrl } from "../../services/api";
import { LazyDocumentPreview } from "../documents/LazyDocumentPreview";
import {
  closeAttachmentPreview,
  getAttachmentPreviewState,
  subscribeAttachmentPreview,
} from "./attachmentPreviewStore";
import type { PluginRuntimeContributionStates } from "../../extensions/coreContributions";

export function AttachmentPreviewHost({
  runtimePlugins,
}: {
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  const [, forceRender] = useState(0);
  const previewStateRef = useRef(getAttachmentPreviewState());

  useEffect(() => {
    const syncPreviewState = () => {
      previewStateRef.current = getAttachmentPreviewState();
      forceRender((count) => count + 1);
    };

    return subscribeAttachmentPreview(syncPreviewState);
  }, []);

  const previewState = previewStateRef.current;
  const attachment = previewState?.attachment ?? null;

  return (
    <DelayedUnmount show={!!attachment}>
      {attachment && (
        <LazyDocumentPreview
          path={attachment.name}
          s3Key={attachment.key}
          fileSize={attachment.size}
          mimeType={attachment.mimeType}
          registryKey={`attachment-preview:${
            previewState?.source ?? "unknown"
          }:${attachment.key}`}
          imageUrl={
            attachment.type === "image" ? getFullUrl(attachment.url) : undefined
          }
          onClose={closeAttachmentPreview}
          mobileFillViewport
          runtimePlugins={runtimePlugins}
        />
      )}
    </DelayedUnmount>
  );
}
