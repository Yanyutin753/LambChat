import { useState } from "react";
import { clsx } from "clsx";
import { Copy, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AttachmentCard, ImageViewer } from "../../common";
import type { MessageAttachment } from "../../../types";
import DocumentPreview from "../../documents/DocumentPreview";
import { getFullUrl } from "../../../services/api";
import { MarkdownContent } from "./MarkdownContent";

// User message bubble component (with copy function, supports markdown rendering) - ChatGPT style
export function UserMessageBubble({
  content,
  attachments,
}: {
  content?: string;
  attachments?: MessageAttachment[];
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [previewAttachment, setPreviewAttachment] =
    useState<MessageAttachment | null>(null);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);

  const handleCopy = async () => {
    if (!content) return;
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Render attachment preview - use file card style uniformly
  const renderAttachments = () => {
    if (!attachments || attachments.length === 0) return null;

    return (
      <div className="flex flex-row justify-end flex-wrap gap-2 sm:gap-3 mb-2">
        {attachments.map((attachment) => {
          const isImage =
            attachment.mimeType?.startsWith("image/") && attachment.url;

          return (
            <AttachmentCard
              key={attachment.id}
              attachment={attachment}
              variant="preview"
              size="default"
              onClick={() => {
                if (isImage && attachment.url) {
                  setImageViewerSrc(getFullUrl(attachment.url) ?? null);
                } else {
                  setPreviewAttachment(attachment);
                }
              }}
            />
          );
        })}
      </div>
    );
  };

  const hasAttachments = attachments && attachments.length > 0;
  const hasContent = content && content.trim().length > 0;

  return (
    <div className="w-full px-2 py-1.5 sm:px-4 mb-3 sm:mb-4 group">
      <div className="mx-auto flex max-w-3xl xl:max-w-5xl justify-end px-2">
        <div className="flex flex-col items-end max-w-[90%]">
          {/* Attachment preview - outside message bubble */}
          {hasAttachments && renderAttachments()}

          {/* Message bubble */}
          {hasContent && (
            <div className="rounded-3xl max-w-full px-5 py-3 bg-gray-50 dark:bg-stone-800 shadow-sm">
              <div className="leading-relaxed text-[15px] sm:text-base text-stone-700 dark:text-stone-300">
                <MarkdownContent content={content!} />
              </div>
            </div>
          )}

          {/* Action buttons - show on hover */}
          <div className="flex justify-end mt-2 gap-1">
            <button
              onClick={handleCopy}
              className={clsx(
                "p-1.5 rounded-lg transition-all duration-200",
                "opacity-0 group-hover:opacity-100",
                "hover:bg-black/5 dark:hover:bg-white/5",
                copied
                  ? "text-emerald-500 dark:text-emerald-400"
                  : "text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300",
              )}
              title={copied ? t("chat.message.copied") : t("chat.message.copy")}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
        </div>
      </div>

      {/* File preview modal */}
      {previewAttachment && (
        <DocumentPreview
          path={previewAttachment.name}
          s3Key={previewAttachment.key}
          fileSize={previewAttachment.size}
          onClose={() => setPreviewAttachment(null)}
          imageUrl={
            previewAttachment.type === "image"
              ? getFullUrl(previewAttachment.url)
              : undefined
          }
        />
      )}

      {/* Image viewer for direct image preview */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
    </div>
  );
}
