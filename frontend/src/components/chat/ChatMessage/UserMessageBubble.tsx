import { useState } from "react";
import { clsx } from "clsx";
import { Copy, Check, GitBranch, Clock, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AttachmentCard, ImageViewer } from "../../common";
import type { MessageAttachment } from "../../../types";
import { getFullUrl } from "../../../services/api";
import { MarkdownContent } from "./MarkdownContent";
import { openAttachmentPreview } from "../attachmentPreviewStore";
import { getUserMessageActionButtonVisibilityClass } from "./userMessageBubbleState";
import { copyToClipboard } from "../../../utils/clipboard";
import { useSessionImageGallery } from "./sessionImageGallery";
import { SkillChip } from "../SkillChip";
import { RunModeChip } from "../richComposer/RunModeChip";
import { FileReferenceChip } from "../richComposer/FileReferenceChip";
import { splitUserMessageFileReferences } from "./userMessageFileReferences";
import { cancelSteeredMessage } from "../steerCancelStore";

// User message bubble component (with copy function, supports markdown rendering) - ChatGPT style
export function UserMessageBubble({
  content,
  attachments,
  onFork,
  isLastMessage,
  enabledSkills,
  runModes,
  queued,
  deferred,
  failed,
  messageId,
}: {
  content?: string;
  attachments?: MessageAttachment[];
  onFork?: () => void;
  isLastMessage?: boolean;
  enabledSkills?: string[];
  /** 发送时激活的运行模式（自动 / 目标），在消息内回显 chip */
  runModes?: Array<"auto" | "goal">;
  /** 运行中插话的排队态：送达前置灰 + 时钟角标，可取消 */
  queued?: boolean;
  /** 当前任务结束后作为下一条普通消息发送 */
  deferred?: boolean;
  /** steer API failed; retain the draft instead of silently sending it later */
  failed?: boolean;
  messageId?: string;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const sessionImageGallery = useSessionImageGallery();

  const handleCopy = async () => {
    if (!content) return;
    await copyToClipboard(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenAttachment = (attachment: MessageAttachment) => {
    const isImage = attachment.mimeType?.startsWith("image/") && attachment.url;
    if (isImage && attachment.url) {
      const src = getFullUrl(attachment.url) ?? attachment.url;
      sessionImageGallery?.openImage(src, attachment.name);
      if (!sessionImageGallery) setImageViewerSrc(src);
      return;
    }
    openAttachmentPreview(attachment, "user-message");
  };

  // Render attachment preview - use file card style uniformly
  const renderAttachments = () => {
    if (!attachments || attachments.length === 0) return null;

    return (
      <div className="flex flex-row justify-end flex-wrap gap-2 sm:gap-3 mb-2">
        {attachments.map((attachment) => {
          return (
            <AttachmentCard
              key={attachment.id}
              attachment={attachment}
              variant="preview"
              size="default"
              onClick={() => handleOpenAttachment(attachment)}
            />
          );
        })}
      </div>
    );
  };

  const hasAttachments = attachments && attachments.length > 0;
  const hasContent = content && content.trim().length > 0;
  const inlineSegments = splitUserMessageFileReferences(
    content ?? "",
    attachments,
  );

  return (
    <div className="w-full px-4 sm:px-10 py-4 group">
      <div className="mx-auto flex max-w-4xl lg:max-w-5xl xl:max-w-6xl justify-end">
        <div
          className={`flex flex-col items-end max-w-[90%] transition-opacity ${
            queued ? "opacity-70" : ""
          }`}
        >
          {/* 排队中的插话：时钟角标 + 取消 */}
          {queued && (
            <div
              className="mb-1 flex items-center gap-1.5 text-xs"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              <Clock size={12} style={{ color: "var(--theme-primary)" }} />
              <span>{t("chat.steerQueued", "已排队，当前步骤后送达")}</span>
              <button
                type="button"
                onClick={() =>
                  content && cancelSteeredMessage(content, messageId)
                }
                className="rounded-full p-0.5 opacity-60 transition hover:opacity-100"
                title={t("chat.steerCancel", "取消这条插话")}
                aria-label={t("chat.steerCancel", "取消这条插话")}
              >
                <X size={12} />
              </button>
            </div>
          )}
          {deferred && !queued && (
            <div
              className="mb-1 text-xs"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {t("chat.steerNext", "当前任务结束后发送")}
            </div>
          )}
          {failed && !queued && !deferred && (
            <div
              className="mb-1 text-xs"
              style={{ color: "var(--theme-error, #b42318)" }}
            >
              {t("chat.steerFailedRetry", "插话发送失败，请检查网络后重试")}
            </div>
          )}

          {/* Attachment preview - outside message bubble */}
          {hasAttachments && renderAttachments()}

          {/* Message bubble */}
          {hasContent && (
            <div
              className="max-w-full px-5 py-2.5 shadow-sm border transition-shadow duration-200 hover:-translate-y-px"
              style={{
                background:
                  "linear-gradient(135deg, var(--theme-primary-light), var(--theme-bg))",
                borderColor: "var(--theme-border)",
                borderRadius: "var(--radius-chat)",
                boxShadow: "var(--shadow-low)",
              }}
            >
              <div
                className="user-message-inline-markdown leading-relaxed text-15 sm:text-base"
                style={{ color: "var(--theme-text)" }}
              >
                {/* Run-mode chips - inline with content, ahead of skill chips */}
                {runModes && runModes.length > 0 && (
                  <span className="skill-chip-row align-baseline">
                    {runModes.map((modeKey) => (
                      <RunModeChip key={modeKey} modeKey={modeKey} readOnly />
                    ))}
                  </span>
                )}
                {/* Skill chips - inline with content */}
                {enabledSkills && enabledSkills.length > 0 && (
                  <span className="skill-chip-row align-baseline">
                    {enabledSkills.map((skillName) => (
                      <SkillChip key={skillName} name={skillName} tags={[]} />
                    ))}
                  </span>
                )}
                <span className="inline leading-relaxed min-w-0">
                  {inlineSegments.map((segment, index) =>
                    segment.kind === "file" ? (
                      <FileReferenceChip
                        key={`file-${segment.attachment.id}-${index}`}
                        referenceId={`sent-${segment.attachment.id}`}
                        fileName={segment.fileName}
                        referenceNumber={segment.referenceNumber}
                        category="document"
                        status="ready"
                        readOnly
                        onClick={() => handleOpenAttachment(segment.attachment)}
                      />
                    ) : segment.value ? (
                      <MarkdownContent
                        key={`text-${index}`}
                        content={segment.value}
                      />
                    ) : null,
                  )}
                </span>
              </div>
            </div>
          )}

          {/* Action buttons - show on hover */}
          <div className="flex justify-end mt-2 gap-1">
            {onFork && (
              <button
                onClick={onFork}
                className={clsx(
                  "p-1.5 rounded-lg transition-colors duration-200",
                  getUserMessageActionButtonVisibilityClass(isLastMessage),
                  "hover:bg-black/5 dark:hover:bg-white/5",
                  "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
                )}
                title={t("chat.message.fork")}
              >
                <GitBranch size={16} />
              </button>
            )}
            <button
              onClick={handleCopy}
              className={clsx(
                "p-1.5 rounded-lg transition-colors duration-200",
                getUserMessageActionButtonVisibilityClass(isLastMessage),
                "hover:bg-black/5 dark:hover:bg-white/5",
                copied
                  ? "text-emerald-500 dark:text-emerald-400"
                  : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
              )}
              title={copied ? t("chat.message.copied") : t("chat.message.copy")}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
        </div>
      </div>

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
