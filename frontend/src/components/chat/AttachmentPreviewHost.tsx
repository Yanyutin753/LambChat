import { useSyncExternalStore } from "react";
import { getFullUrl } from "../../services/api";
import { LazyDocumentPreview } from "../documents/LazyDocumentPreview";
import {
  closeAttachmentPreview,
  getAttachmentPreviewTabs,
  subscribeAttachmentPreview,
  attachmentPreviewKey,
} from "./attachmentPreviewStore";

export function AttachmentPreviewHost() {
  const previews = useSyncExternalStore(
    subscribeAttachmentPreview,
    getAttachmentPreviewTabs,
    getAttachmentPreviewTabs,
  );
  return previews.map((preview) => {
    const { attachment } = preview;
    const key = attachmentPreviewKey(preview);
    return (
      <LazyDocumentPreview
        key={key}
        path={attachment.name}
        s3Key={attachment.key}
        fileSize={attachment.size}
        mimeType={attachment.mimeType}
        registryKey={key}
        imageUrl={
          attachment.type === "image" ? getFullUrl(attachment.url) : undefined
        }
        onClose={() => closeAttachmentPreview(key)}
        mobileFillViewport
      />
    );
  });
}
