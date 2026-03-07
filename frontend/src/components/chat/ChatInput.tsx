import { useState, useRef, useEffect, memo } from "react";
import {
  ArrowUp,
  Square,
  Lock,
  Brain,
  Zap,
  Settings,
  ChevronDown,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { ToolSelector } from "../selectors/ToolSelector";
import { SkillSelector } from "../selectors/SkillSelector";
import { FileUploadButton } from "./FileUploadButton";
import { uploadApi, getFullUrl } from "../../services/api";
import DocumentPreview from "../documents/DocumentPreview";
import { AttachmentCard } from "../common/AttachmentCard";
import { ImageViewer } from "../common";
import type {
  ToolState,
  ToolCategory,
  SkillResponse,
  SkillSource,
  AgentOption,
  MessageAttachment,
  FileCategory,
} from "../../types";

// Helper to get file category from MIME type
function getFileCategory(file: File): FileCategory {
  const type = file.type.toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
}

// Icon mapping for dynamic icon rendering
const ICON_MAP: Record<string, LucideIcon> = {
  Brain,
  Zap,
  Settings,
};

interface ChatInputProps {
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
  enableMcp?: boolean;
  // Skills
  skills?: SkillResponse[];
  onToggleSkill?: (name: string) => Promise<void>;
  onToggleSkillCategory?: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<void>;
  onToggleAllSkills?: (enabled: boolean) => Promise<void>;
  skillsLoading?: boolean;
  enabledSkillsCount?: number;
  totalSkillsCount?: number;
  enableSkills?: boolean;
  // Agent options
  agentOptions?: Record<string, AgentOption>;
  agentOptionValues?: Record<string, boolean | string | number>;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
}

// Agent option toggle/select button component
interface AgentOptionButtonProps {
  optionKey: string;
  option: AgentOption;
  value: boolean | string | number;
  onChange: (value: boolean | string | number) => void;
}

const AgentOptionButton = memo(function AgentOptionButton({
  optionKey: _optionKey,
  option,
  value,
  onChange,
}: AgentOptionButtonProps) {
  const { t } = useTranslation();
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Get label with i18n support
  const label = option.label_key ? t(option.label_key) : option.label;
  const description = option.description_key
    ? t(option.description_key)
    : option.description || label;

  // Get icon component
  const IconComponent = option.icon ? ICON_MAP[option.icon] : null;

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showDropdown) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setShowDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showDropdown]);

  // Boolean toggle button
  if (option.type === "boolean") {
    const isActive = value === true;
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`flex items-center justify-center rounded-full p-2 border transition-all duration-300 ${
          isActive
            ? "border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300"
            : "border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300"
        }`}
        title={description}
      >
        {IconComponent ? <IconComponent size={18} /> : <Settings size={18} />}
      </button>
    );
  }

  // Select/dropdown for string/number options
  if (option.options && option.options.length > 0) {
    const selectedOption = option.options.find((opt) => opt.value === value);
    const selectedLabel = selectedOption?.label || String(value);

    return (
      <div className="relative" ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
          className={`flex items-center gap-1 rounded-full px-2 py-1.5 border text-sm transition-all duration-300 ${
            showDropdown || value !== option.default
              ? "border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300"
              : "border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300"
          }`}
          title={description}
        >
          {IconComponent && <IconComponent size={14} />}
          <span className="max-w-[80px] truncate">{selectedLabel}</span>
          <ChevronDown size={14} />
        </button>

        {showDropdown && (
          <div className="absolute bottom-full left-0 mb-1 z-50 min-w-[120px] rounded-lg bg-white dark:bg-stone-800 shadow-lg border border-gray-200 dark:border-stone-700 overflow-hidden">
            {option.options.map((opt) => (
              <button
                key={String(opt.value)}
                type="button"
                onClick={() => {
                  onChange(opt.value);
                  setShowDropdown(false);
                }}
                className={`w-full px-3 py-2 text-left text-sm transition-colors ${
                  value === opt.value
                    ? "bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300"
                    : "hover:bg-gray-100 dark:hover:bg-stone-700 text-gray-700 dark:text-stone-300"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Default: simple toggle button
  return (
    <button
      type="button"
      onClick={() =>
        onChange(value === option.default ? !option.default : option.default)
      }
      className={`flex items-center justify-center rounded-full p-2 border transition-all duration-300 ${
        value !== option.default
          ? "border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300"
          : "border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300"
      }`}
      title={description}
    >
      {IconComponent ? <IconComponent size={18} /> : <Settings size={18} />}
    </button>
  );
});

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
  enableMcp = true,
  // Skills
  skills = [],
  onToggleSkill,
  onToggleSkillCategory,
  onToggleAllSkills,
  skillsLoading: _skillsLoading,
  enabledSkillsCount = 0,
  totalSkillsCount = 0,
  enableSkills = true,
  // Agent options
  agentOptions,
  agentOptionValues = {},
  onToggleAgentOption,
}: ChatInputProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const [previewAttachment, setPreviewAttachment] =
    useState<MessageAttachment | null>(null);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200,
      )}px`;
    }
  }, [input]);

  // Handle paste to convert rich text to plain text
  const handlePaste = (e: React.ClipboardEvent) => {
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    // Get rich text (HTML)
    const htmlText = clipboardData.getData("text/html");

    if (htmlText) {
      // Convert HTML to plain text with basic formatting preserved as markdown-like
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = htmlText;

      // Convert to markdown-like format
      const processNode = (node: Node): string => {
        if (node.nodeType === Node.TEXT_NODE) {
          return node.textContent || "";
        }
        if (node.nodeType === Node.ELEMENT_NODE) {
          const el = node as HTMLElement;
          const children = Array.from(el.childNodes).map(processNode).join("");

          switch (el.tagName) {
            case "B":
            case "STRONG":
              return `**${children}**`;
            case "I":
            case "EM":
              return `*${children}*`;
            case "U":
              return `<u>${children}</u>`;
            case "S":
            case "STRIKE":
            case "DEL":
              return `~~${children}~~`;
            case "A":
              return `[${children}](${el.getAttribute("href") || ""})`;
            case "CODE":
              return `\`${children}\``;
            case "PRE":
              return `\n\`\`\`\n${children}\n\`\`\`\n`;
            case "BLOCKQUOTE":
              return `> ${children}`;
            case "LI":
              return `- ${children}`;
            case "UL":
            case "OL":
              return children;
            case "BR":
              return "\n";
            case "DIV":
            case "P":
              return children + "\n";
            default:
              return children;
          }
        }
        return "";
      };

      const markdownText = processNode(tempDiv).trim();

      // Insert at cursor position
      e.preventDefault();
      const textarea = textareaRef.current;
      if (textarea) {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const newValue =
          input.substring(0, start) + markdownText + input.substring(end);
        setInput(newValue);

        // Set cursor position after inserted text
        setTimeout(() => {
          textarea.selectionStart = textarea.selectionEnd =
            start + markdownText.length;
          textarea.focus();
        }, 0);
      }
    }
    // If no HTML, let default paste handle plain text
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    if (input.trim() && !isLoading && !disabled) {
      onSend(input.trim(), agentOptionValues, attachments);
      setInput("");
      setAttachments([]); // 发送后清空附件
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      // 如果正在加载，按 Enter 应该停止而不是发送
      if (isLoading) {
        onStop();
      } else {
        handleSubmit(e);
      }
    }
  };

  const hasContent = input.trim() && !disabled;
  const canSubmit = hasContent && canSend && !isLoading;

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);

    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;

    // Upload files directly with progress tracking
    for (const file of Array.from(files)) {
      const uploadId = crypto.randomUUID();
      const tempId = `temp-${uploadId}`;

      // Add temporary attachment to show progress immediately
      const tempAttachment: MessageAttachment = {
        id: tempId,
        key: "",
        name: file.name,
        type: getFileCategory(file),
        mimeType: file.type,
        size: file.size,
        url: "",
      };

      setAttachments((prev) => [...prev, tempAttachment]);

      try {
        const result = await uploadApi.uploadFile(file, {
          onProgress: (progress) => {
            // Update attachment with progress
            setAttachments((prev) =>
              prev.map((a) =>
                a.id === tempId
                  ? { ...a, uploadProgress: progress, isUploading: true }
                  : a,
              ),
            );
          },
        });

        const finalAttachment: MessageAttachment = {
          id: crypto.randomUUID(),
          key: result.key,
          name: result.name || file.name,
          type: result.type as FileCategory,
          mimeType: result.mimeType,
          size: result.size,
          url: result.url,
        };

        // Replace temp with final attachment
        setAttachments((prev) =>
          prev.map((a) => (a.id === tempId ? finalAttachment : a)),
        );
      } catch (error) {
        console.error("Upload failed:", error);
        // Remove temp attachment on error
        setAttachments((prev) => prev.filter((a) => a.id !== tempId));
      }
    }
  };

  return (
    <div className="px-3 sm:px-4 pb-4 sm:pb-5 dark:bg-stone-900">
      <form onSubmit={handleSubmit} className="mx-auto max-w-3xl xl:max-w-5xl">
        {/* ChatGPT-style container */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`flex flex-col relative w-full rounded-3xl px-1 bg-white dark:bg-stone-800 border shadow-[0_0_10px_rgba(0,0,0,0.05)] dark:shadow-[0_0_10px_rgba(0,0,0,0.1)] transition-all duration-200 ${
            isDraggingOver
              ? "border-purple-400 dark:border-purple-500 border-2 border-dashed"
              : "border-gray-200/50 dark:border-stone-700/50"
          }`}
        >
          {/* Attachment preview - top area (ChatGPT style) */}
          {attachments.length > 0 && (
            <div className="mx-2 mt-2 -mb-1 flex flex-wrap gap-2">
              {attachments.map((attachment) => {
                const isImage =
                  attachment.mimeType?.startsWith("image/") && attachment.url;

                const handleRemove = () => {
                  // Immediately remove from local state for better UX
                  setAttachments((prev) =>
                    prev.filter((a) => a.id !== attachment.id),
                  );
                  // Async delete from server (non-blocking)
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
                        setPreviewAttachment(attachment);
                      }
                    }}
                    onRemove={handleRemove}
                  />
                );
              })}
            </div>
          )}

          {/* Textarea section */}
          <div className="px-2.5 py-2 flex items-start gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={
                canSend ? t("chat.placeholder") : t("chat.noPermission")
              }
              disabled={disabled || !canSend}
              className="scrollbar-hide bg-transparent dark:text-stone-100 outline-none flex-1 pt-3 px-1 resize-none text-sm text-gray-900 placeholder-gray-400 dark:placeholder-stone-500 disabled:opacity-50"
              rows={1}
            />
          </div>

          {/* Bottom toolbar */}
          <div className="flex justify-between pt-3 pb-3 px-2 mx-0.5 max-w-full">
            {/* Left side - Tool buttons grouped together */}
            <div className="flex items-center gap-2 self-end flex-1 min-w-0">
              {/* File upload button */}
              <FileUploadButton
                attachments={attachments}
                onAttachmentsChange={setAttachments}
              />
              {/* Other tool buttons in scrollable container */}
              <div className="flex items-center gap-2 overflow-x-auto overflow-y-hidden scrollbar-none flex-1">
                {/* Tool selector button */}
                {enableMcp &&
                  onToggleTool &&
                  onToggleCategory &&
                  onToggleAll && (
                    <ToolSelector
                      tools={tools}
                      onToggleTool={onToggleTool}
                      onToggleCategory={onToggleCategory}
                      onToggleAll={onToggleAll}
                      enabledCount={enabledToolsCount}
                      totalCount={totalToolsCount}
                    />
                  )}
                {/* Skill selector button */}
                {enableSkills &&
                  onToggleSkill &&
                  onToggleSkillCategory &&
                  onToggleAllSkills && (
                    <SkillSelector
                      skills={skills}
                      onToggleSkill={onToggleSkill}
                      onToggleCategory={onToggleSkillCategory}
                      onToggleAll={onToggleAllSkills}
                      enabledCount={enabledSkillsCount}
                      totalCount={totalSkillsCount}
                    />
                  )}
                {/* Agent options - Multiple options support */}
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

            {/* Right side - Send/Stop button */}
            <div className="self-end flex space-x-1.5 flex-shrink-0">
              {!canSend ? (
                <div
                  className="flex items-center justify-center rounded-full p-2 bg-gray-100 text-gray-400 dark:bg-stone-700 dark:text-stone-500"
                  title={t("chat.noPermission")}
                >
                  <Lock size={18} />
                </div>
              ) : isLoading ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onStop();
                  }}
                  className="flex items-center justify-center rounded-full p-2 bg-stone-900 dark:bg-stone-600 text-white dark:text-stone-100 transition-all hover:scale-105"
                  title={t("chat.stop")}
                >
                  <Square size={16} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className={`flex items-center justify-center rounded-full p-2 transition-all ${
                    canSubmit
                      ? "bg-stone-900 dark:bg-stone-600 text-white dark:text-stone-100 hover:scale-105"
                      : "bg-gray-100 text-gray-400 dark:bg-stone-700 dark:text-stone-500"
                  }`}
                  title={t("chat.send")}
                >
                  <ArrowUp size={18} />
                </button>
              )}
            </div>
          </div>
        </div>
      </form>

      {/* 文件预览弹窗 */}
      {previewAttachment && (
        <DocumentPreview
          path={previewAttachment.name}
          s3Key={previewAttachment.key}
          fileSize={previewAttachment.size}
          imageUrl={
            previewAttachment.type === "image"
              ? getFullUrl(previewAttachment.url)
              : undefined
          }
          onClose={() => setPreviewAttachment(null)}
        />
      )}

      {/* 图片预览器 - 直接预览图片 */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
    </div>
  );
});
