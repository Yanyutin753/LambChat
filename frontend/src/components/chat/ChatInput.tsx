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
import TurndownService from "turndown";
import { useTranslation } from "react-i18next";
import { ToolSelector } from "../selectors/ToolSelector";
import { SkillSelector } from "../selectors/SkillSelector";
import { FileUploadButton } from "./FileUploadButton";
import { uploadApi, getFullUrl } from "../../services/api";
import DocumentPreview from "../documents/DocumentPreview";
import { AttachmentCard } from "../common/AttachmentCard";
import { ImageViewer } from "../common";
import { useFileUpload } from "../../hooks/useFileUpload";
import type {
  ToolState,
  ToolCategory,
  SkillResponse,
  SkillSource,
  AgentOption,
  MessageAttachment,
} from "../../types";

/** Shared turndown instance — created once, reused on every paste. */
const turndown = new TurndownService({
  headingStyle: "atx",
  hr: "---",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "*",
  strongDelimiter: "**",
});

// Enhance turndown with better rules for common copy-paste scenarios

// Remove empty links, images, and spans that carry no content
turndown.addRule("removeEmpty", {
  filter: (node: HTMLElement) => {
    return (
      (node.nodeName === "A" || node.nodeName === "SPAN") &&
      !node.textContent?.trim()
    );
  },
  replacement: () => "",
});

// Preserve tables as Markdown tables
turndown.addRule("table", {
  filter: "table",
  replacement: (_content: string, node: HTMLElement) => {
    const table = node as HTMLTableElement;
    const rows: string[][] = [];
    table.querySelectorAll("tr").forEach((tr) => {
      const cells: string[] = [];
      tr.querySelectorAll("th, td").forEach((cell) => {
        cells.push(
          turndown.turndown(cell.innerHTML).trim().replace(/\n/g, " "),
        );
      });
      rows.push(cells);
    });
    if (rows.length === 0) return "";

    // Normalize column count
    const colCount = Math.max(...rows.map((r) => r.length));
    const normalized = rows.map((r) =>
      r.length < colCount ? [...r, ...Array(colCount - r.length).fill("")] : r,
    );

    // Calculate column widths
    const colWidths = Array(colCount).fill(0);
    normalized.forEach((row) =>
      row.forEach((cell, i) => {
        colWidths[i] = Math.max(colWidths[i], cell.length);
      }),
    );

    const pad = (s: string, w: number) =>
      s + " ".repeat(Math.max(0, w - s.length));
    const padRight = (s: string, w: number) =>
      s.length > w ? s.substring(0, w - 1) + "…" : pad(s, w);

    let md = "";
    normalized.forEach((row, ri) => {
      md +=
        "| " +
        row.map((c, ci) => padRight(c, colWidths[ci])).join(" | ") +
        " |\n";
      if (ri === 0) {
        md += "| " + colWidths.map((w) => "-".repeat(w)).join(" | ") + " |\n";
      }
    });
    return md.trim() ? "\n\n" + md + "\n" : "";
  },
});

// Better code block handling — detect language hints from class names
turndown.addRule("fencedCodeBlock", {
  filter: (node: HTMLElement): boolean => {
    return !!(
      node.nodeName === "PRE" &&
      node.firstChild &&
      (node.firstChild as HTMLElement).nodeName === "CODE"
    );
  },
  replacement: (_content: string, node: HTMLElement) => {
    const codeEl = node.firstChild as HTMLElement;
    const className = codeEl.className || "";
    const langMatch = className.match(/(?:language-|lang-|hljs\s+)(\w+)/);
    const lang = langMatch ? langMatch[1] : "";
    const code = codeEl.textContent || "";
    return "\n\n```" + lang + "\n" + code.replace(/\n$/, "") + "\n```\n\n";
  },
});

// Clean up pasted content: remove inline styles, empty paragraphs, etc.
function cleanPastedHtml(div: HTMLDivElement) {
  // Remove non-content elements
  div
    .querySelectorAll("meta, style, script, title, link")
    .forEach((el) => el.remove());

  // Remove empty paragraphs and divs
  div.querySelectorAll("p, div").forEach((el) => {
    if (!el.textContent?.trim() && !el.querySelector("img")) {
      el.remove();
    }
  });

  // Remove class/id attributes (they carry no semantic meaning for markdown)
  div.querySelectorAll("*").forEach((el) => {
    el.removeAttribute("class");
    el.removeAttribute("id");
    el.removeAttribute("style");
    el.removeAttribute("data-");
  });

  // Unwrap <div> and <section> that are just wrappers
  div.querySelectorAll("div, section").forEach((el) => {
    const parent = el.parentNode;
    if (!parent) return;
    while (el.firstChild) {
      parent.insertBefore(el.firstChild, el);
    }
    parent.removeChild(el);
  });

  // Convert <br> inside <li> to newlines for better list handling
  div.querySelectorAll("li br").forEach((br) => {
    br.replaceWith(document.createTextNode("\n"));
  });
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
  // External attachments (for page-level drag and drop)
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
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
  attachments: externalAttachments,
  onAttachmentsChange: externalOnAttachmentsChange,
}: ChatInputProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [internalAttachments, setInternalAttachments] = useState<
    MessageAttachment[]
  >([]);
  const [previewAttachment, setPreviewAttachment] =
    useState<MessageAttachment | null>(null);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Use external attachments if provided, otherwise use internal state
  const attachments = externalAttachments ?? internalAttachments;
  const setAttachments = externalOnAttachmentsChange ?? setInternalAttachments;

  const { uploadFiles, validateCount, cancelUpload } = useFileUpload({
    attachments,
    onAttachmentsChange: setAttachments,
  });

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        250,
      )}px`;
    }
  }, [input]);

  // Handle paste to convert rich text to plain text or upload pasted files
  const handlePaste = (e: React.ClipboardEvent) => {
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    // Check for pasted files first (screenshots, copied files)
    if (clipboardData.files && clipboardData.files.length > 0) {
      e.preventDefault();
      if (!validateCount(clipboardData.files.length)) return;

      uploadFiles(clipboardData.files);
      return;
    }

    // Get rich text (HTML)
    const htmlText = clipboardData.getData("text/html");

    if (htmlText) {
      e.preventDefault();

      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = htmlText;

      // Clean up common copy-paste artifacts (Word, Google Docs, etc.)
      cleanPastedHtml(tempDiv);

      const markdownText = turndown.turndown(tempDiv);

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
        }, 0);
      }
    }
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
  // Check if any attachment is still uploading
  const hasUploadingAttachment = attachments.some((a) => a.isUploading);
  const canSubmit =
    hasContent && canSend && !isLoading && !hasUploadingAttachment;

  // Drag and drop handlers (no stopPropagation — page-level listeners in AppContent handle the overlay)
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
    <div className="px-3 sm:px-4 pb-4 sm:pb-5 dark:bg-stone-900">
      <form onSubmit={handleSubmit} className="mx-auto max-w-3xl xl:max-w-5xl">
        {/* ChatGPT-style container */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`chat-input-container flex flex-col relative w-full rounded-2xl px-1 bg-white dark:bg-stone-800 border transition-all duration-300 ${
            isDraggingOver
              ? "border-stone-400 dark:border-stone-500 border-2 border-dashed shadow-lg shadow-stone-200/50 dark:shadow-stone-900/50"
              : "border-stone-200/70 dark:border-stone-700/60 shadow-[0_2px_12px_rgba(0,0,0,0.06)] dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]"
          }`}
        >
          {/* Attachment preview - top area (ChatGPT style) */}
          {attachments.length > 0 && (
            <div className="mx-2 mt-2 -mb-1 flex gap-2 overflow-x-auto">
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
              className="bg-transparent dark:text-stone-100 outline-none flex-1 pt-2 px-1 resize-none text-[15px] text-gray-900 placeholder-stone-400 dark:placeholder-stone-500 disabled:opacity-50 leading-relaxed overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
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
                  className="flex items-center justify-center rounded-full p-2 bg-stone-100 text-stone-400 dark:bg-stone-700 dark:text-stone-500"
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
                  className="flex items-center justify-center rounded-full p-2 bg-stone-800 dark:bg-stone-500 text-white dark:text-stone-100 transition-all duration-200 hover:scale-105 active:scale-95 shadow-md"
                  title={t("chat.stop")}
                >
                  <Square size={16} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className={`flex items-center justify-center rounded-full p-2 transition-all duration-200 ${
                    canSubmit
                      ? "bg-stone-800 dark:bg-stone-500 text-white dark:text-stone-100 hover:scale-105 active:scale-95 shadow-md hover:shadow-lg"
                      : "bg-stone-100 text-stone-400 dark:bg-stone-700 dark:text-stone-500"
                  }`}
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
