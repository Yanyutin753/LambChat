import { useEffect, useRef, useState } from "react";
import DocumentPreview from "../documents/DocumentPreview";
import { DelayedUnmount } from "../common/DelayedUnmount";
import { getFullUrl } from "../../services/api";
import {
  closeAttachmentPreview,
  getAttachmentPreviewState,
  subscribeAttachmentPreview,
} from "./attachmentPreviewStore";

export function AttachmentPreviewHost() {
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
        <DocumentPreview
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
        />
      )}
    </DelayedUnmount>
  );
}
