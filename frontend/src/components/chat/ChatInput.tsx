import { useState, useRef, useEffect, useCallback, memo } from "react";
import { createPortal } from "react-dom";
import toast from "react-hot-toast";
import {
  ArrowUp,
  Square,
  Ban,
  Lock,
  Brain,
  Zap,
  Settings,
  FileText,
  type LucideIcon,
} from "lucide-react";
import TurndownService from "turndown";
import { useTranslation } from "react-i18next";
import { ToolSelector } from "../selectors/ToolSelector";
import { SkillSelector } from "../selectors/SkillSelector";
import { AgentModeSelector } from "../selectors/AgentModeSelector";
import { FileUploadButton } from "./FileUploadButton";
import { uploadApi, getFullUrl } from "../../services/api";
import DocumentPreview from "../documents/DocumentPreview";
import { DelayedUnmount } from "../common/DelayedUnmount";
import { AttachmentCard } from "../common/AttachmentCard";
import { ImageViewer } from "../common";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { useFileUpload } from "../../hooks/useFileUpload";
import {
  getTextareaMaxHeightPx,
  resizeTextareaForContent,
} from "./chatInputViewport";
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

/** When pasted text exceeds this length, auto-convert to a .txt file upload. */
const PASTE_TEXT_THRESHOLD = 3000;

const THINKING_LEVEL_COLOR: Record<
  string,
  { border: string; bg: string; text: string }
> = {
  off: {
    border: "transparent",
    bg: "transparent",
    text: "var(--theme-text-secondary)",
  },
  low: {
    border: "color-mix(in srgb, #60a5fa 40%, transparent)",
    bg: "color-mix(in srgb, #60a5fa 10%, transparent)",
    text: "#60a5fa",
  },
  medium: {
    border: "color-mix(in srgb, #fbbf24 40%, transparent)",
    bg: "color-mix(in srgb, #fbbf24 10%, transparent)",
    text: "#fbbf24",
  },
  high: {
    border: "color-mix(in srgb, #fb923c 40%, transparent)",
    bg: "color-mix(in srgb, #fb923c 10%, transparent)",
    text: "#fb923c",
  },
  max: {
    border: "color-mix(in srgb, #f472b6 40%, transparent)",
    bg: "color-mix(in srgb, #f472b6 10%, transparent)",
    text: "#f472b6",
  },
};

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
  const portalRef = useRef<HTMLDivElement>(null);
  const mobileSheetRef = useRef<HTMLDivElement>(null);

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
      const target = event.target as Node;
      if (
        dropdownRef.current?.contains(target) ||
        portalRef.current?.contains(target) ||
        mobileSheetRef.current?.contains(target)
      ) {
        return;
      }
      setShowDropdown(false);
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
          isActive ? "chat-tool-btn-active" : "chat-tool-btn"
        }`}
        title={description}
      >
        {IconComponent ? <IconComponent size={18} /> : <Settings size={18} />}
      </button>
    );
  }

  // Select/dropdown for string/number options
  const options = option.options;
  if (options && options.length > 0) {
    const selectedOption = options.find((opt) => opt.value === value);
    const selectedLabel = selectedOption?.label_key
      ? t(selectedOption.label_key)
      : selectedOption?.label || String(value);

    const getDropdownStyle = (): React.CSSProperties => {
      const rect = dropdownRef.current?.getBoundingClientRect();
      if (!rect) return { display: "none" };
      const vw = window.innerWidth;
      const dropdownW = Math.min(288, vw - 16);
      const left = Math.max(8, Math.min(rect.left, vw - dropdownW - 8));
      return {
        position: "fixed",
        bottom: window.innerHeight - rect.top + 4,
        left,
        width: dropdownW,
        zIndex: 9999,
      };
    };

    const ActiveIcon = IconComponent || Brain;
    const isOff = String(value) === "off";
    const levelColor =
      THINKING_LEVEL_COLOR[String(value)] ?? THINKING_LEVEL_COLOR.off;

    return (
      <div ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
          className="chat-tool-btn"
          style={
            isOff
              ? undefined
              : {
                  borderColor: levelColor.border,
                  background: levelColor.bg,
                  color: levelColor.text,
                }
          }
          title={`${description}: ${selectedLabel}`}
        >
          <ActiveIcon size={18} />
        </button>

        {showDropdown &&
          createPortal(
            <>
              {/* Mobile: bottom sheet modal */}
              <div
                ref={mobileSheetRef}
                className="sm:hidden fixed inset-0 z-[9999] flex flex-col justify-end"
                onClick={() => setShowDropdown(false)}
              >
                <div className="absolute inset-0 bg-black/40" />
                <div
                  className="relative rounded-t-2xl px-4 pt-3 pb-6 animate-in fade-in slide-in-from-bottom-4 duration-200"
                  style={{
                    background: "var(--theme-bg-card)",
                    maxHeight: "60vh",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Handle */}
                  <div
                    className="mx-auto mb-3 w-9 h-1 rounded-full"
                    style={{ background: "var(--theme-border)" }}
                  />
                  {/* Title */}
                  <div
                    className="text-sm font-medium mb-3"
                    style={{ color: "var(--theme-text)" }}
                  >
                    {description}
                  </div>
                  {/* Options */}
                  <div className="flex flex-col gap-1">
                    {options.map((opt) => {
                      const isActive = opt.value === value;
                      const optColor =
                        THINKING_LEVEL_COLOR[String(opt.value)] ??
                        THINKING_LEVEL_COLOR.off;
                      return (
                        <button
                          key={String(opt.value)}
                          type="button"
                          onClick={() => {
                            onChange(opt.value);
                            setShowDropdown(false);
                          }}
                          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors text-left active:scale-[0.98]"
                          style={{
                            background: isActive
                              ? `color-mix(in srgb, ${optColor.text} 12%, transparent)`
                              : "transparent",
                            color: isActive
                              ? optColor.text
                              : "var(--theme-text)",
                          }}
                        >
                          <span
                            className="w-2.5 h-2.5 rounded-full shrink-0"
                            style={{
                              background: isActive
                                ? optColor.text
                                : "var(--theme-border)",
                            }}
                          />
                          {opt.label_key
                            ? t(opt.label_key)
                            : opt.label || String(opt.value)}
                          {isActive && (
                            <span
                              className="ml-auto text-xs"
                              style={{ color: optColor.text }}
                            >
                              ✓
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Desktop: dropdown with stepped slider */}
              <div
                ref={portalRef}
                className="hidden sm:block w-72 rounded-xl px-2 py-1.5 border shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-200"
                style={{
                  ...getDropdownStyle(),
                  background: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                }}
              >
                {/* Title */}
                <div
                  className="px-2.5 py-1.5 text-xs font-medium"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {description}
                </div>

                {/* Stepped slider */}
                <div className="mx-2 mb-1">
                  <div className="stepped-slider select-none">
                    <div
                      className="relative h-10 flex items-center cursor-pointer"
                      role="slider"
                      tabIndex={0}
                      aria-valuemin={0}
                      aria-valuemax={options.length - 1}
                      aria-valuenow={options.findIndex(
                        (opt) => opt.value === value,
                      )}
                      onClick={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const clientX = (e.nativeEvent as MouseEvent).clientX;
                        const ratio = Math.max(
                          0,
                          Math.min(1, (clientX - rect.left) / rect.width),
                        );
                        const idx = Math.round(ratio * (options.length - 1));
                        const opt = options[idx];
                        if (opt) onChange(opt.value);
                      }}
                      onKeyDown={(e) => {
                        const currentIdx = options.findIndex(
                          (opt) => opt.value === value,
                        );
                        if (
                          e.key === "ArrowRight" &&
                          currentIdx < options.length - 1
                        ) {
                          onChange(options[currentIdx + 1].value);
                        } else if (e.key === "ArrowLeft" && currentIdx > 0) {
                          onChange(options[currentIdx - 1].value);
                        }
                      }}
                    >
                      {/* Track background */}
                      <div
                        className="absolute left-0 right-0 h-1 rounded-full"
                        style={{
                          background: "var(--theme-border)",
                        }}
                      />
                      {/* Active track — fills up to current dot */}
                      <div
                        className="absolute left-0 h-1 rounded-full transition-all duration-150"
                        style={{
                          width: `${
                            (options.findIndex((opt) => opt.value === value) /
                              (options.length - 1)) *
                            100
                          }%`,
                          background:
                            levelColor.text ?? "var(--theme-text-secondary)",
                        }}
                      />
                      {/* Step dots */}
                      {options.map((opt, idx) => {
                        const pos = (idx / (options.length - 1)) * 100;
                        const isActive = opt.value === value;
                        return (
                          <div
                            key={String(opt.value)}
                            className="absolute w-1.5 h-1.5 rounded-full -translate-x-1/2 transition-colors duration-150"
                            style={{
                              left: `${pos}%`,
                              background: isActive
                                ? levelColor.text ??
                                  "var(--theme-text-secondary)"
                                : "var(--theme-text-secondary)",
                              opacity: isActive ? 1 : 0.5,
                            }}
                          />
                        );
                      })}
                      {/* Active thumb */}
                      <div
                        className="absolute w-4 h-4 rounded-full -translate-x-1/2 transition-all duration-150 shadow-sm hover:scale-105"
                        style={{
                          left: `${
                            (options.findIndex((opt) => opt.value === value) /
                              (options.length - 1)) *
                            100
                          }%`,
                          background:
                            levelColor.text ?? "var(--theme-text-secondary)",
                          border: "2px solid var(--theme-bg-card)",
                        }}
                      />
                    </div>
                    {/* Step labels */}
                    <div className="relative h-4 -mt-1">
                      {options.map((opt, idx) => {
                        const pos = (idx / (options.length - 1)) * 100;
                        const isActive = opt.value === value;
                        return (
                          <button
                            key={String(opt.value)}
                            type="button"
                            onClick={() => onChange(opt.value)}
                            className="absolute text-[10px] leading-tight text-center transition-all duration-150 cursor-pointer -translate-x-1/2 whitespace-nowrap"
                            style={{
                              left: `${pos}%`,
                              color: isActive
                                ? levelColor.text ??
                                  "var(--theme-text-secondary)"
                                : "var(--theme-text-secondary)",
                              fontWeight: isActive ? 500 : 400,
                            }}
                          >
                            {opt.label_key
                              ? t(opt.label_key)
                              : opt.label || String(opt.value)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </>,
            document.body,
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
        value !== option.default ? "chat-tool-btn-active" : "chat-tool-btn"
      }`}
      title={description}
    >
      {IconComponent ? <IconComponent size={18} /> : <Settings size={18} />}
    </button>
  );
});

// Agent mode modal selector
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
  const [previewAttachment, setPreviewAttachment] =
    useState<MessageAttachment | null>(null);
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

  // Use external attachments if provided, otherwise use internal state
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
    // Use rAF to ensure the DOM has updated before measuring scrollHeight
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

    // Plain text paste — check length before inserting
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
    <div
      className="sm:px-4 pb-3"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="mx-auto max-w-3xl xl:max-w-5xl px-2"
      >
        {/* ChatGPT-style container */}
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
          {/* Attachment preview - top area (ChatGPT style) */}
          {attachments.length > 0 && (
            <div className="mx-3 mt-2.5 -mb-1 flex gap-3 overflow-x-auto attachment-scroll pb-1">
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
                      pendingSkillNames={pendingSkillNames}
                      isMutating={skillsMutating}
                      enabledCount={enabledSkillsCount}
                      totalCount={totalSkillsCount}
                    />
                  )}
                {/* Agent mode selector */}
                <AgentModeSelector
                  agents={agents}
                  currentAgent={currentAgent || ""}
                  onSelectAgent={onSelectAgent}
                />
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

      {/* Keyboard shortcut hint — desktop only */}
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

      {/* 文件预览弹窗 */}
      <DelayedUnmount show={!!previewAttachment}>
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
      </DelayedUnmount>

      {/* 图片预览器 - 直接预览图片 */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}

      {/* 停止生成确认框 */}
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

      {/* 联系管理员弹窗 */}
      <ContactAdminDialog
        isOpen={contactAdminOpen}
        onClose={() => setContactAdminOpen(false)}
        reason="noPermission"
      />
    </div>
  );
});
