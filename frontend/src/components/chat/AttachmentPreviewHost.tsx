import { useSyncExternalStore } from "react";
import { getFullUrl } from "../../services/api";
import { getOwnUploadFileUrl } from "../../services/api/uploadFileUrl";
import { decodeToken } from "../../services/api/token";
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
    const token = getOwnUploadFileUrl(attachment.url)?.searchParams.get(
      "file_token",
    );
    const shareId = token ? decodeToken(token)?.share_id : undefined;
    // Share access must keep its capability; owner attachments renew by storage key.
    const sharedUrl =
      typeof shareId === "string" && shareId ? attachment.url : undefined;
    return (
      <LazyDocumentPreview
        key={key}
        path={attachment.name}
        s3Key={attachment.key}
        signedUrl={sharedUrl}
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
