import { useState, useRef, useEffect, useCallback, memo } from "react";
import toast from "react-hot-toast";
import { ArrowUp, Square, Ban, Lock, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ToolSelector } from "../selectors/ToolSelector";
import { SkillSelector } from "../selectors/SkillSelector";
import { AgentModeSelector } from "../selectors/AgentModeSelector";
import { FileUploadButton } from "./FileUploadButton";
import { uploadApi, getFullUrl } from "../../services/api";
import { AttachmentCard } from "../common/AttachmentCard";
import { ImageViewer } from "../common";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { useFileUpload } from "../../hooks/useFileUpload";
import { openAttachmentPreview } from "./attachmentPreviewStore";
import {
  getTextareaMaxHeightPx,
  resizeTextareaForContent,
} from "./chatInputViewport";
import { AgentOptionButton } from "./AgentOptionButton";
import { turndown, cleanPastedHtml } from "./chatInputTurndown";
import { PASTE_TEXT_THRESHOLD } from "./chatInputConstants";
import type {
  ToolState,
  ToolCategory,
  SkillResponse,
  SkillSource,
  AgentOption,
  MessageAttachment,
} from "../../types";

export interface ChatInputProps {
  onSend: (
    message: string,
    options?: Record<string, boolean | string | number>,
    attachments?: MessageAttachment[],
  ) => void;
  onStop: () => void;
  isLoading: boolean;
  disabled?: boolean;
  canSend?: boolean;
  tools?: ToolState[];
  onToggleTool?: (toolName: string) => void;
  onToggleCategory?: (category: ToolCategory, enabled: boolean) => void;
  onToggleAll?: (enabled: boolean) => void;
  toolsLoading?: boolean;
  enabledToolsCount?: number;
  totalToolsCount?: number;
  // Skills
  skills?: SkillResponse[];
  onToggleSkill?: (name: string) => Promise<boolean>;
  onToggleSkillCategory?: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<boolean>;
  onToggleAllSkills?: (enabled: boolean) => Promise<boolean>;
  skillsLoading?: boolean;
  pendingSkillNames?: string[];
  skillsMutating?: boolean;
  enabledSkillsCount?: number;
  totalSkillsCount?: number;
  enableSkills?: boolean;
  // Agent options
  agentOptions?: Record<string, AgentOption>;
  agentOptionValues?: Record<string, boolean | string | number>;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
  // Agent mode selector
  agents?: { id: string; name: string; description: string }[];
  currentAgent?: string;
  onSelectAgent?: (id: string) => void;
  // External attachments (for page-level drag and drop)
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
}

export const ChatInput = memo(function ChatInput({
  onSend,
  onStop,
  isLoading,
  disabled,
  canSend = true,
  tools = [],
  onToggleTool,
  onToggleCategory,
  onToggleAll,
  toolsLoading: _toolsLoading,
  enabledToolsCount = 0,
  totalToolsCount = 0,
  // Skills
  skills = [],
  onToggleSkill,
  onToggleSkillCategory,
  onToggleAllSkills,
  skillsLoading: _skillsLoading,
  pendingSkillNames = [],
  skillsMutating = false,
  enabledSkillsCount = 0,
  totalSkillsCount = 0,
  enableSkills = true,
  // Agent options
  agentOptions,
  agentOptionValues = {},
  onToggleAgentOption,
  // Agent mode selector
  agents = [],
  currentAgent,
  onSelectAgent,
  attachments: externalAttachments,
  onAttachmentsChange: externalOnAttachmentsChange,
}: ChatInputProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [internalAttachments, setInternalAttachments] = useState<
    MessageAttachment[]
  >([]);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);
  const [contactAdminOpen, setContactAdminOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resizeRafRef = useRef<number>(0);
  const [history, setHistory] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem("chatInputHistory");
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const historyIndexRef = useRef(-1);
  const draftRef = useRef("");

  const attachments = externalAttachments ?? internalAttachments;
  const setAttachments = externalOnAttachmentsChange ?? setInternalAttachments;

  const { uploadFiles, validateCount, cancelUpload } = useFileUpload({
    attachments,
    onAttachmentsChange: setAttachments,
  });

  const resizeTextareaHeightNow = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    resizeTextareaForContent(
      el,
      getTextareaMaxHeightPx({
        isMobile:
          typeof window !== "undefined" ? window.innerWidth < 640 : false,
        viewportHeight:
          typeof window !== "undefined"
            ? window.visualViewport?.height ?? window.innerHeight
            : null,
      }),
    );
  }, []);

  const scheduleTextareaResize = useCallback(() => {
    if (typeof window === "undefined") return;
    cancelAnimationFrame(resizeRafRef.current);
    resizeRafRef.current = requestAnimationFrame(resizeTextareaHeightNow);
  }, [resizeTextareaHeightNow]);

  const resetTextareaHeight = useCallback(() => {
    resizeTextareaHeightNow();
  }, [resizeTextareaHeightNow]);

  useEffect(() => {
    requestAnimationFrame(resetTextareaHeight);
  }, [input, resetTextareaHeight]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const updateTextareaSize = () => {
      scheduleTextareaResize();
    };

    updateTextareaSize();
    window.visualViewport?.addEventListener("resize", updateTextareaSize);
    window.addEventListener("resize", updateTextareaSize);
    window.addEventListener("orientationchange", updateTextareaSize);

    return () => {
      window.visualViewport?.removeEventListener("resize", updateTextareaSize);
      window.removeEventListener("resize", updateTextareaSize);
      window.removeEventListener("orientationchange", updateTextareaSize);
    };
  }, [scheduleTextareaResize]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(resizeRafRef.current);
    };
  }, []);

  const textAsFile = useCallback(
    (text: string, mimeType: string, ext: string) => {
      if (!validateCount(1)) return;
      const now = new Date();
      const ts = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, "0"),
        String(now.getDate()).padStart(2, "0"),
        String(now.getHours()).padStart(2, "0"),
        String(now.getMinutes()).padStart(2, "0"),
        String(now.getSeconds()).padStart(2, "0"),
      ].join("");
      const name = `clipboard-${ts}.${ext}`;
      const file = new File([text], name, { type: mimeType });
      uploadFiles([file], "document");
      toast.custom(() => (
        <div
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium"
          style={{
            background:
              "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
            border:
              "1px solid color-mix(in srgb, var(--theme-primary) 20%, transparent)",
            color: "var(--theme-primary)",
          }}
        >
          <FileText size={16} className="shrink-0" />
          <span>{t("chat.textAutoUploaded", "长文本已自动转为文件上传")}</span>
        </div>
      ));
    },
    [validateCount, uploadFiles, t],
  );

  const handlePaste = (e: React.ClipboardEvent) => {
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    if (clipboardData.files && clipboardData.files.length > 0) {
      e.preventDefault();
      if (!validateCount(clipboardData.files.length)) return;

      uploadFiles(clipboardData.files);
      return;
    }

    const htmlText = clipboardData.getData("text/html");

    if (htmlText) {
      e.preventDefault();

      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = htmlText;

      cleanPastedHtml(tempDiv);

      const markdownText = turndown.turndown(tempDiv);

      if (markdownText.length > PASTE_TEXT_THRESHOLD) {
        textAsFile(markdownText, "text/markdown", "md");
        return;
      }

      const textarea = textareaRef.current;
      if (textarea) {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const newValue =
          input.substring(0, start) + markdownText + input.substring(end);
        setInput(newValue);

        setTimeout(() => {
          textarea.selectionStart = textarea.selectionEnd =
            start + markdownText.length;
          textarea.focus();
          scheduleTextareaResize();
        }, 0);
      }
      return;
    }

    const plainText = clipboardData.getData("text/plain");
    if (plainText && plainText.length > PASTE_TEXT_THRESHOLD) {
      e.preventDefault();
      textAsFile(plainText, "text/plain", "txt");
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    if (input.trim() && !isLoading && !disabled) {
      const trimmed = input.trim();
      onSend(trimmed, agentOptionValues, attachments);
      setHistory((prev) => {
        const next = [...prev, trimmed].slice(-200);
        try {
          localStorage.setItem("chatInputHistory", JSON.stringify(next));
        } catch {
          /* storage full or unavailable */
        }
        return next;
      });
      historyIndexRef.current = -1;
      draftRef.current = "";
      setInput("");
      setAttachments([]);
      requestAnimationFrame(() => {
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const newlineModifier = localStorage.getItem("newlineModifier") || "shift";

    if (e.key === "Enter") {
      const needsModifier = newlineModifier === "ctrl" ? e.ctrlKey : e.shiftKey;

      if (needsModifier) {
        return;
      }

      e.preventDefault();
      if (isLoading) {
        setStopConfirmOpen(true);
      } else {
        handleSubmit(e);
      }
      return;
    }

    if (history.length === 0) return;

    const textarea = textareaRef.current;
    const atTop =
      textarea?.selectionStart === 0 && textarea?.selectionEnd === 0;
    const value = textarea?.value ?? "";
    const atBottom =
      textarea?.selectionStart === value.length &&
      textarea?.selectionEnd === value.length;

    if (e.key === "ArrowUp" && atTop) {
      e.preventDefault();
      if (historyIndexRef.current === -1) {
        draftRef.current = input;
      }
      const newIndex = Math.min(
        historyIndexRef.current + 1,
        history.length - 1,
      );
      historyIndexRef.current = newIndex;
      setInput(history[history.length - 1 - newIndex]);
      requestAnimationFrame(() => {
        if (textarea) {
          textarea.selectionStart = textarea.selectionEnd =
            history[history.length - 1 - newIndex].length;
        }
      });
    } else if (
      e.key === "ArrowDown" &&
      (atBottom || historyIndexRef.current !== -1)
    ) {
      e.preventDefault();
      const newIndex = historyIndexRef.current - 1;
      if (newIndex < 0) {
        historyIndexRef.current = -1;
        setInput(draftRef.current);
        draftRef.current = "";
      } else {
        historyIndexRef.current = newIndex;
        setInput(history[history.length - 1 - newIndex]);
      }
      requestAnimationFrame(() => {
        if (textarea) {
          textarea.selectionStart = textarea.selectionEnd =
            textarea.value.length;
        }
      });
    }
  };

  const hasContent = input.trim() && !disabled;
  const hasUploadingAttachment = attachments.some((a) => a.isUploading);
  const canSubmit =
    hasContent && canSend && !isLoading && !hasUploadingAttachment;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(false);

    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;

    if (!validateCount(files.length)) return;

    uploadFiles(files);
  };

  return (
    <div
      className="sm:px-4 pb-3"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="mx-auto max-w-3xl xl:max-w-5xl px-2"
      >
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`chat-input-container flex flex-col relative w-full rounded-3xl px-1 border transition-all duration-300 ${
            isDraggingOver ? "border-dashed shadow-lg border-2" : ""
          }`}
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: isDraggingOver
              ? "var(--theme-primary)"
              : "var(--theme-border)",
            boxShadow: isDraggingOver
              ? undefined
              : "0 2px 12px rgba(0,0,0,0.06)",
          }}
        >
          {attachments.length > 0 && (
            <div className="mx-3 mt-2.5 -mb-1 flex gap-3 overflow-x-auto attachment-scroll pb-1">
              {attachments.map((attachment) => {
                const isImage =
                  attachment.mimeType?.startsWith("image/") && attachment.url;

                const handleRemove = () => {
                  setAttachments((prev) =>
                    prev.filter((a) => a.id !== attachment.id),
                  );
                  uploadApi.deleteFile(attachment.key).catch((error) => {
                    console.error("Failed to delete file from server:", error);
                  });
                };

                return (
                  <AttachmentCard
                    key={attachment.id}
                    attachment={attachment}
                    variant="editable"
                    size="compact"
                    isUploading={attachment.isUploading}
                    onClick={() => {
                      if (isImage && attachment.url) {
                        setImageViewerSrc(getFullUrl(attachment.url) ?? null);
                      } else {
                        openAttachmentPreview(attachment, "chat-input");
                      }
                    }}
                    onRemove={handleRemove}
                    onCancel={
                      attachment.isUploading
                        ? () => cancelUpload(attachment.id)
                        : undefined
                    }
                  />
                );
              })}
            </div>
          )}

          <div className="px-2.5 py-2 flex items-start gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={scheduleTextareaResize}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={
                canSend ? t("chat.placeholder") : t("chat.noPermission")
              }
              disabled={disabled || !canSend}
              className="bg-transparent outline-none flex-1 pt-2.5 px-1 resize-none text-[15px] disabled:opacity-50 leading-relaxed overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none] min-h-[52px]"
              style={{ color: "var(--theme-text)" }}
              rows={1}
            />
          </div>

          <div className="flex justify-between pt-3 pb-3 px-2 mx-0.5 max-w-full">
            <div className="flex items-center gap-2 self-end flex-1 min-w-0">
              <FileUploadButton
                attachments={attachments}
                onAttachmentsChange={setAttachments}
              />
              <div className="flex items-center gap-2 overflow-x-auto overflow-y-hidden scrollbar-none flex-1">
                {onToggleTool && onToggleCategory && onToggleAll && (
                  <ToolSelector
                    tools={tools}
                    onToggleTool={onToggleTool}
                    onToggleCategory={onToggleCategory}
                    onToggleAll={onToggleAll}
                    enabledCount={enabledToolsCount}
                    totalCount={totalToolsCount}
                  />
                )}
                {enableSkills &&
                  onToggleSkill &&
                  onToggleSkillCategory &&
                  onToggleAllSkills && (
                    <SkillSelector
                      skills={skills}
                      onToggleSkill={onToggleSkill}
                      onToggleCategory={onToggleSkillCategory}
                      onToggleAll={onToggleAllSkills}
                      pendingSkillNames={pendingSkillNames}
                      isMutating={skillsMutating}
                      enabledCount={enabledSkillsCount}
                      totalCount={totalSkillsCount}
                    />
                  )}
                <AgentModeSelector
                  agents={agents}
                  currentAgent={currentAgent || ""}
                  onSelectAgent={onSelectAgent}
                />
                {agentOptions &&
                  onToggleAgentOption &&
                  Object.keys(agentOptions).length > 0 && (
                    <>
                      {Object.entries(agentOptions).map(([key, option]) => (
                        <AgentOptionButton
                          key={key}
                          optionKey={key}
                          option={option}
                          value={agentOptionValues[key] ?? option.default}
                          onChange={(value) => onToggleAgentOption(key, value)}
                        />
                      ))}
                    </>
                  )}
              </div>
            </div>

            <div className="self-end flex space-x-1.5 flex-shrink-0">
              {!canSend ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setContactAdminOpen(true);
                  }}
                  className="flex items-center justify-center rounded-full p-2 cursor-pointer transition-all duration-200 hover:scale-105"
                  style={{
                    backgroundColor: "var(--theme-primary-light)",
                    color: "var(--theme-text-secondary)",
                  }}
                  title={t("chat.noPermission")}
                >
                  <Lock size={18} />
                </button>
              ) : isLoading ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setStopConfirmOpen(true);
                  }}
                  className="chat-tool-btn-active flex items-center justify-center rounded-full p-2 transition-all duration-300 hover:scale-105 active:scale-95"
                  style={{
                    borderColor: "color-mix(in srgb, #fbbf24 40%, transparent)",
                    background: "color-mix(in srgb, #fbbf24 10%, transparent)",
                    color: "#fbbf24",
                  }}
                  title={t("chat.stop")}
                >
                  <Square size={16} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className={`flex items-center justify-center rounded-full p-2 transition-all duration-300 ${
                    canSubmit ? "hover:scale-105 active:scale-95" : ""
                  }`}
                  style={{
                    backgroundColor: "transparent",
                    border: canSubmit
                      ? "1px solid color-mix(in srgb, var(--theme-primary) 40%, transparent)"
                      : "1px solid var(--theme-border)",
                    color: canSubmit
                      ? "var(--theme-primary)"
                      : "var(--theme-text-secondary)",
                  }}
                  title={
                    hasUploadingAttachment
                      ? t("chat.waitingForUpload", "请等待文件上传完成")
                      : t("chat.send")
                  }
                >
                  <ArrowUp size={18} />
                </button>
              )}
            </div>
          </div>
        </div>
      </form>

      <div className="hidden sm:flex mx-auto max-w-3xl xl:max-w-5xl mt-3 px-2 justify-center">
        <span
          className="text-xs"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {localStorage.getItem("newlineModifier") === "ctrl"
            ? t("chat.sendHintCtrl")
            : t("chat.sendHintShift")}
        </span>
      </div>

      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}

      <ConfirmDialog
        isOpen={stopConfirmOpen}
        title={t("chat.stopConfirmTitle")}
        message={t("chat.stopConfirmMessage")}
        confirmText={t("chat.stop")}
        cancelText={t("common.cancel")}
        variant="warning"
        onConfirm={() => {
          setStopConfirmOpen(false);
          onStop();
          toast.custom(() => (
            <div
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium"
              style={{
                background:
                  "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
                border:
                  "1px solid color-mix(in srgb, var(--theme-primary) 20%, transparent)",
                color: "var(--theme-primary)",
              }}
            >
              <Ban size={16} className="shrink-0" />
              <span>{t("chat.status.cancelled")}</span>
            </div>
          ));
        }}
        onCancel={() => setStopConfirmOpen(false)}
      />

      <ContactAdminDialog
        isOpen={contactAdminOpen}
        onClose={() => setContactAdminOpen(false)}
        reason="noPermission"
      />
    </div>
  );
});
