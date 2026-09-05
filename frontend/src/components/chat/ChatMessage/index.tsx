import { clsx } from "clsx";
import { useEffect, useRef, useState, memo } from "react";
import { createPortal } from "react-dom";
import toast from "react-hot-toast";
import {
  Check,
  ChevronDown,
  Copy,
  GitBranch,
  Info,
  Loader2,
  Target,
} from "lucide-react";
import { useStickyDropdownPosition } from "../../../hooks/useStickyDropdownPosition";
import type {
  Message,
  MessagePart,
  ToolCall,
  ToolResult,
  TokenUsagePart,
} from "../../../types";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "./MarkdownContent";
import { ToolCallItem } from "./ToolCallItem";
import { UserMessageBubble } from "./UserMessageBubble";
import { BookmarkButton } from "./BookmarkButton";
import { buildBookmarkLabel } from "../../../utils/bookmarks";
import { MessagePartRenderer } from "./MessagePartRenderer";
import {
  isRevealFileImagePart,
  type RevealFileImageInfo,
} from "./revealFileImageUtils";
import { MessageImageGallery } from "./MessageImageGallery";
import { RevealArtifactsSummary } from "./RevealArtifactsSummary";
import { RunStepsCollapse } from "./RunStepsCollapse";
import {
  countRunSteps,
  getRunElapsedMs,
  getRunStartedAtMs,
  splitRunTailGroups,
} from "./runStepsCollapseUtils";
import { FeedbackButtons } from "./FeedbackButtons";
import { AssistantAvatar } from "./AssistantAvatar";
import { ShareButton } from "./ShareButton";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { useAuth } from "../../../hooks/useAuth";
import { ModelIconImg } from "../../agent/modelIcon.tsx";
import { shouldCloseTokenDetailsPopover } from "./tokenDetailsPopoverGuards";
import { resolveTokenUsageModelDetails } from "./tokenUsageModel";
import {
  buildCostDetailRows,
  formatCostDetailRow,
  hasPricedCost,
} from "./tokenCostDisplay";
import { cacheHitRateFromTokens } from "../todayUsageSnapshot";
import { useFxRates } from "../../../hooks/useFxRates";
import { formatCostUsd, type FxRatesDoc } from "../../../utils/currency";
import {
  shouldAllowAutoPreviewForPart,
  type AutoPreviewTarget,
} from "./autoPreviewEligibility";
import type { RevealPreviewRequest } from "./items/revealPreviewData";
import type { RevealPreviewOpenSource } from "./items/revealPreviewState";
import type { ActiveGoalSpec } from "../../../hooks/useAgent/types";
import { createMessageAnchorId } from "../../layout/AppContent/messageOutline";
import { formatDateTime, formatDateTimeShort } from "../../../utils/datetime";
import { copyToClipboard } from "../../../utils/clipboard";
import { shouldShowGoalDetailsForMessage } from "../goalVisibility";
import { areChatMessagePropsEqual } from "./messageMemo";
import { hasPendingAskHuman } from "../../../hooks/useAgent/messageParts";

interface ChatMessageProps {
  message: Message;
  sessionId?: string;
  runId?: string;
  isLastMessage?: boolean;
  onStop?: () => void;
  personaAvatar?: string | null;
  personaName?: string | null;
  activePreview?: RevealPreviewRequest | null;
  latestAutoPreview?: AutoPreviewTarget | null;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  onForkMessage?: (messageId: string) => void | Promise<void>;
  onRecommendQuestionClick?: (question: string) => void;
  onRetryCancelledMessage?: (messageId: string) => void | Promise<void>;
  showFeedbackAndShareActions?: boolean;
  activeGoal?: ActiveGoalSpec | null;
  isFirst?: boolean;
}

// Token usage statistics button component - ChatGPT style
function TokenDetailsButton({
  tokenUsage,
  duration,
  timestamp,
  modelDetails,
  fxRates,
  language,
}: {
  tokenUsage?: TokenUsagePart;
  duration?: number;
  timestamp?: Date;
  modelDetails?: {
    name: string;
    value: string;
    provider?: string;
    icon?: string;
  } | null;
  fxRates?: FxRatesDoc | null;
  language?: string;
}) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const [costExpanded, setCostExpanded] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  // 口径与今日用量卡一致：分母取有效 prompt 输入并 clamp ≤1，
  // 兼容 input_tokens 不含缓存 token 的 provider。
  const cacheRate = tokenUsage
    ? cacheHitRateFromTokens(
        tokenUsage.input_tokens ?? 0,
        tokenUsage.cache_read_tokens ?? 0,
        tokenUsage.cache_creation_tokens ?? 0,
      )
    : null;
  const costRows = buildCostDetailRows(tokenUsage);
  const priced = hasPricedCost(tokenUsage);
  const costRowLabels: Record<string, string> = {
    input: t("chat.message.tokenInput"),
    output: t("chat.message.tokenOutput"),
    cache_read: t("chat.message.tokenCacheRead"),
    cache_write: t("chat.message.tokenCacheCreation"),
  };

  const popupStyle = useStickyDropdownPosition(
    buttonRef,
    showDetails,
    (rect) => {
      const popupHeight = popupRef.current?.offsetHeight ?? 300;
      const popupWidth = Math.min(popupRef.current?.offsetWidth ?? 280, 360);
      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;
      const flipBelow = spaceAbove < popupHeight + 8 && spaceBelow > spaceAbove;
      const desiredTop = flipBelow
        ? rect.bottom + 8
        : rect.top - 8 - popupHeight;
      // 钳制在视口内：上方空间不足时绝不溢出顶部，下方同理
      const top = Math.max(
        8,
        Math.min(desiredTop, window.innerHeight - popupHeight - 8),
      );
      const left = Math.max(
        8,
        Math.min(rect.left, window.innerWidth - popupWidth - 8),
      );

      return {
        position: "fixed",
        left,
        top,
      };
    },
    costExpanded,
  );

  // Close details when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        shouldCloseTokenDetailsPopover(
          event.target as Node | null,
          buttonRef.current,
          popupRef.current,
        )
      ) {
        setShowDetails(false);
      }
    };
    if (showDetails) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDetails]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => setShowDetails(!showDetails)}
        className={clsx(
          "p-1.5 rounded-md transition-colors",
          "hover:bg-stone-200 dark:hover:bg-stone-700",
          "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
        )}
        title={t("chat.message.tokenUsage")}
      >
        <Info size={16} />
      </button>
      {/* ChatGPT style details popup */}
      {showDetails &&
        createPortal(
          <div
            ref={popupRef}
            style={popupStyle}
            className={clsx(
              "z-[100] min-w-[150px] max-w-[calc(100vw-1rem)] w-auto p-3 rounded-lg shadow-lg",
              "bg-theme-bg-card",
              "border border-theme-border",
              "whitespace-nowrap",
            )}
          >
            <div className="text-xs space-y-1.5">
              {tokenUsage && (
                <>
                  <div className="flex justify-between gap-4 text-sky-600 dark:text-sky-400">
                    <span className="text-theme-text-secondary">
                      {t("chat.message.tokenInput")}
                    </span>
                    <span className="font-medium">
                      {tokenUsage.input_tokens?.toLocaleString()} tokens
                    </span>
                  </div>
                  <div className="flex justify-between gap-4 text-violet-600 dark:text-violet-400">
                    <span className="text-theme-text-secondary">
                      {t("chat.message.tokenOutput")}
                    </span>
                    <span className="font-medium">
                      {tokenUsage.output_tokens?.toLocaleString()} tokens
                    </span>
                  </div>
                  {(tokenUsage.cache_creation_tokens ?? 0) > 0 && (
                    <div className="flex justify-between gap-4 text-emerald-600 dark:text-emerald-400">
                      <span className="text-theme-text-secondary">
                        {t("chat.message.tokenCacheCreation")}
                      </span>
                      <span className="font-medium">
                        {(
                          tokenUsage.cache_creation_tokens ?? 0
                        ).toLocaleString()}{" "}
                        tokens
                      </span>
                    </div>
                  )}
                  {cacheRate !== null && cacheRate > 0 && (
                    <div className="flex justify-between gap-4 text-fuchsia-600 dark:text-fuchsia-400">
                      <span className="text-theme-text-secondary">
                        {t("chat.message.tokenCacheRate")}
                      </span>
                      <span className="font-medium">
                        {(cacheRate * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                  {(tokenUsage.cache_read_tokens ?? 0) > 0 && (
                    <div className="flex justify-between gap-4 text-pink-600 dark:text-pink-400">
                      <span className="text-theme-text-secondary">
                        {t("chat.message.tokenCacheRead")}
                      </span>
                      <span className="font-medium">
                        {(tokenUsage.cache_read_tokens ?? 0).toLocaleString()}{" "}
                        tokens
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between gap-4 border-t border-theme-border pt-1.5 mt-1.5 text-amber-600 dark:text-amber-400">
                    <span className="text-theme-text-secondary">
                      {t("chat.message.tokenTotal")}
                    </span>
                    <span className="font-medium">
                      {tokenUsage.total_tokens?.toLocaleString()} tokens
                    </span>
                  </div>
                  {priced && (
                    <div className="border-t border-theme-border pt-1.5 mt-1.5 space-y-1.5">
                      <div className="flex justify-between gap-4 text-amber-600 dark:text-amber-400">
                        <button
                          type="button"
                          onClick={() => setCostExpanded(!costExpanded)}
                          aria-expanded={costExpanded}
                          title={t("chat.message.costDetail")}
                          className="flex items-center gap-0.5 transition-colors hover:text-amber-700 dark:hover:text-amber-300"
                        >
                          <span>{t("chat.message.costTotal")}</span>
                          <ChevronDown
                            size={12}
                            className={clsx(
                              "opacity-50 transition-transform",
                              costExpanded && "rotate-180",
                            )}
                          />
                        </button>
                        <span className="font-medium tabular-nums">
                          {formatCostUsd(tokenUsage.cost_usd ?? 0, {
                            language,
                            rates: fxRates ?? null,
                          })}
                        </span>
                      </div>
                      {costExpanded &&
                        costRows.map((row) => {
                          const { cost, rate } = formatCostDetailRow(row, {
                            language,
                            rates: fxRates ?? null,
                          });
                          return (
                            <div
                              key={row.key}
                              className="flex justify-between gap-4"
                            >
                              <span className="text-theme-text-secondary">
                                {costRowLabels[row.key]}
                              </span>
                              <span className="text-theme-text font-medium tabular-nums">
                                {cost}
                                {rate !== null && (
                                  <span className="ml-1 text-theme-text-tertiary font-normal">
                                    @ {rate}
                                  </span>
                                )}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  )}
                </>
              )}
              {duration && (
                <div className="flex justify-between gap-4 border-t border-theme-border pt-1.5 mt-1.5">
                  <span className="text-theme-text-secondary">
                    {t("chat.message.duration")}
                  </span>
                  <span className="text-theme-text font-medium">
                    {(duration / 1000).toFixed(2)}s
                  </span>
                </div>
              )}
              {modelDetails && (
                <div className="flex justify-between gap-4 border-t border-theme-border pt-1.5 mt-1.5">
                  <span className="text-theme-text-secondary">
                    {t("chat.message.model")}
                  </span>
                  <span className="flex items-center gap-1.5 text-theme-text font-medium">
                    <ModelIconImg
                      model={modelDetails.value}
                      provider={modelDetails.provider}
                      icon={modelDetails.icon}
                      size={16}
                    />
                    <span>{modelDetails.name}</span>
                  </span>
                </div>
              )}
              {timestamp && (
                <div className="flex justify-between gap-4 border-t border-theme-border pt-1.5 mt-1.5">
                  <span className="text-theme-text-secondary">
                    {t("chat.message.startTime")}
                  </span>
                  <span className="text-theme-text font-medium tabular-nums">
                    {formatDateTime(timestamp)}
                  </span>
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function GoalDetailsButton({ goal }: { goal: ActiveGoalSpec }) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  const popupStyle = useStickyDropdownPosition(
    buttonRef,
    showDetails,
    (rect) => {
      const popupHeight = popupRef.current?.offsetHeight ?? 200;
      const popupWidth = 256;
      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;
      const flipBelow = spaceAbove < popupHeight + 8 && spaceBelow > spaceAbove;
      const rightAlign = window.innerWidth - rect.right;
      return {
        position: "fixed",
        top: flipBelow ? rect.bottom + 8 : rect.top - 16,
        right: Math.min(rightAlign, window.innerWidth - popupWidth - 8),
        transform: flipBelow ? "translateY(0)" : "translateY(-100%)",
      };
    },
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        shouldCloseTokenDetailsPopover(
          event.target as Node | null,
          buttonRef.current,
          popupRef.current,
        )
      ) {
        setShowDetails(false);
      }
    };
    if (showDetails) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDetails]);

  const startedAt = goal.started_at
    ? new Date(goal.started_at).getTime()
    : null;
  const endedAt = goal.ended_at ? new Date(goal.ended_at).getTime() : null;

  // Tick every second so the running duration auto-increments.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (goal.ended_at || !showDetails) return;
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [goal.ended_at, showDetails]);

  const effectiveEndedAt = endedAt ?? Date.now();
  const durationText = startedAt
    ? (() => {
        const totalSeconds = Math.max(
          0,
          Math.floor((effectiveEndedAt - startedAt) / 1000),
        );
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(
          2,
          "0",
        )}`;
      })()
    : null;

  const statusLabel = goal.ended_at
    ? t("chat.goal.completed")
    : t("chat.goal.runningStatus");

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => setShowDetails(!showDetails)}
        className={clsx(
          "p-1.5 rounded-md transition-colors",
          "hover:bg-stone-200 dark:hover:bg-stone-700",
          "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
        )}
        title={t("chat.goal.active")}
      >
        <Target size={16} />
      </button>
      {showDetails &&
        Object.keys(popupStyle).length > 0 &&
        createPortal(
          <div
            ref={popupRef}
            style={popupStyle}
            className={clsx(
              "z-[100] w-64 p-3 rounded-lg shadow-lg",
              "bg-theme-bg-card",
              "border border-theme-border",
            )}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <span
                className="text-xs font-medium"
                style={{ color: "var(--theme-primary)" }}
              >
                {t("chat.goal.active")}
              </span>
              <span
                className="text-xs px-1.5 py-0.5 rounded-full font-medium"
                style={{
                  color: "var(--theme-primary)",
                  backgroundColor:
                    "var(--theme-primary-bg, rgba(245,158,11,0.08))",
                }}
              >
                {statusLabel}
              </span>
            </div>
            <p className="text-sm text-theme-text leading-relaxed break-words">
              {goal.objective}
            </p>
            {durationText && (
              <div className="flex justify-between gap-4 border-t border-theme-border pt-1.5 mt-2">
                <span className="text-xs text-theme-text-secondary">
                  {t("chat.goal.duration")}
                </span>
                <span className="text-xs text-theme-text font-medium tabular-nums">
                  {durationText}
                </span>
              </div>
            )}
            {startedAt && (
              <div className="flex justify-between gap-4 pt-1">
                <span className="text-xs text-theme-text-secondary">
                  {t("chat.goal.startedAt")}
                </span>
                <span className="text-xs text-theme-text font-medium tabular-nums">
                  {formatDateTimeShort(new Date(goal.started_at!))}
                </span>
              </div>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}

/** Groups consecutive image reveal_file parts for gallery rendering. */
function groupPartsForGallery(parts: MessagePart[]): Array<
  | {
      type: "gallery";
      images: RevealFileImageInfo[];
      startPartIndex: number;
    }
  | { type: "single"; part: MessagePart; partIndex: number }
> {
  const groups: Array<
    | {
        type: "gallery";
        images: RevealFileImageInfo[];
        startPartIndex: number;
      }
    | { type: "single"; part: MessagePart; partIndex: number }
  > = [];
  let imageBuffer: RevealFileImageInfo[] | null = null;
  let bufferStartIndex = 0;

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];

    // Check if this part is an image reveal_file
    if (part.type === "tool") {
      const imageInfo = isRevealFileImagePart(part);
      if (imageInfo) {
        if (!imageBuffer) {
          imageBuffer = [];
          bufferStartIndex = i;
        }
        imageBuffer.push(imageInfo);
        continue;
      }
    }

    // Non-image part: flush buffer if any
    if (imageBuffer) {
      groups.push({
        type: "gallery",
        images: imageBuffer,
        startPartIndex: bufferStartIndex,
      });
      imageBuffer = null;
    }

    if (part.type !== "recommend_questions") {
      groups.push({ type: "single", part, partIndex: i });
    }
  }

  // Flush remaining buffer
  if (imageBuffer) {
    groups.push({
      type: "gallery",
      images: imageBuffer,
      startPartIndex: bufferStartIndex,
    });
  }

  return groups;
}

export const ChatMessage = memo(function ChatMessage({
  message,
  sessionId,
  runId,
  isLastMessage,
  personaAvatar,
  personaName,
  activePreview,
  latestAutoPreview,
  onOpenPreview,
  onForkMessage,
  onRecommendQuestionClick,
  onRetryCancelledMessage,
  showFeedbackAndShareActions = true,
  activeGoal,
  isFirst,
}: ChatMessageProps) {
  const { t, i18n } = useTranslation();
  const { availableModels } = useSettingsContext();
  const { isAuthenticated } = useAuth();
  const fxRates = useFxRates();
  const isUser = message.role === "user";
  const isStreaming = message.isStreaming && !message.content;
  const [copied, setCopied] = useState(false);
  const [isForking, setIsForking] = useState(false);
  const modelDetails = resolveTokenUsageModelDetails({
    modelId: message.tokenUsage?.model_id,
    model: message.tokenUsage?.model,
    availableModels,
  });

  // If there are parts, render in order; otherwise fall back to old rendering method
  const hasParts = message.parts && message.parts.length > 0;
  const isWaitingForHuman = hasPendingAskHuman(message.parts ?? []);
  // User message: bubble style, right aligned
  if (isUser) {
    return (
      <div
        id={createMessageAnchorId(message.id)}
        data-outline-anchor="true"
        data-outline-id={createMessageAnchorId(message.id)}
        className={clsx(
          "scroll-mt-6 rounded-2xl transition-[box-shadow] duration-300 data-[external-navigation-highlighted=true]:shadow-[0_0_16px_color-mix(in_srgb,var(--theme-primary)_20%,transparent)] space-y-3 sm:space-y-4",
          !isFirst && "pt-2",
        )}
      >
        <UserMessageBubble
          content={message.content}
          attachments={message.attachments}
          isLastMessage={isLastMessage}
          enabledSkills={message.enabledSkills}
          runModes={message.runModes}
          queued={message.metadata?.queued === true}
          deferred={message.metadata?.deferred === true}
          failed={message.metadata?.steerStatus === "failed"}
          messageId={message.id}
          extraActions={
            isAuthenticated && sessionId && !message.isStreaming ? (
              <BookmarkButton
                sessionId={sessionId}
                messageId={message.id}
                runId={message.runId || runId}
                label={buildBookmarkLabel(message.content || "")}
              />
            ) : undefined
          }
        />
      </div>
    );
  }

  // Get assistant message's plain text content for copying
  const getAssistantTextContent = (): string => {
    if (hasParts && message.parts) {
      // Extract all text content from parts
      return message.parts
        .filter(
          (part): part is Extract<MessagePart, { type: "text" }> =>
            part.type === "text",
        )
        .map((part) => part.content)
        .join("\n");
    }
    return message.content || "";
  };

  // 过程折叠区：流式与完成后，除最后的 output_text（及其后的收尾部分）外，
  // 中间过程统一收进「已工作 X 分 X 秒 ›」折叠区（流式默认展开、完成自动收起）
  const runPartGroups = hasParts ? groupPartsForGallery(message.parts!) : [];
  const { head: runHeadGroups, tail: runTailGroups } = splitRunTailGroups(
    runPartGroups,
    { enabled: !isWaitingForHuman },
  );
  const renderPartGroups = (groups: Array<(typeof runPartGroups)[number]>) =>
    groups.map((group) =>
      group.type === "gallery" ? (
        <MessageImageGallery
          key={`gallery-${group.startPartIndex}`}
          images={group.images}
        />
      ) : (
        <MessagePartRenderer
          key={group.partIndex}
          part={group.part}
          messageId={message.id}
          partIndex={group.partIndex}
          isStreaming={message.isStreaming}
          isLast={group.partIndex === message.parts!.length - 1}
          activePreview={activePreview}
          onOpenPreview={onOpenPreview}
          onRecommendQuestionClick={onRecommendQuestionClick}
          onRetryCancelled={
            isLastMessage &&
            group.part.type === "cancelled" &&
            onRetryCancelledMessage
              ? () => void onRetryCancelledMessage(message.id)
              : undefined
          }
          allowAutoPreview={shouldAllowAutoPreviewForPart({
            messageId: message.id,
            partIndex: group.partIndex,
            latestAutoPreview: latestAutoPreview ?? null,
          })}
        />
      ),
    );

  // Assistant message: left layout
  return (
    <div
      id={createMessageAnchorId(message.id)}
      data-outline-anchor="true"
      data-outline-id={createMessageAnchorId(message.id)}
      className={clsx(
        "group w-full scroll-mt-6 rounded-2xl transition-[background-color,box-shadow] duration-300 data-[external-navigation-highlighted=true]:bg-[var(--theme-primary)]/8",
        isLastMessage &&
          message.isStreaming &&
          "animate-[fade-in_0.3s_ease-out]",
        !isFirst && "pt-2",
      )}
    >
      <div className="mx-auto flex flex-col max-w-4xl lg:max-w-5xl xl:max-w-6xl px-4 sm:px-10">
        {/* Content */}
        <div className="min-w-0 min-h-0 py-1 sm:py-2">
          {/* Header: Avatar + Role label + Stop button */}
          <div className="mb-3 flex flex-nowrap items-center gap-2">
            <AssistantAvatar
              className="size-5 sm:size-6 shrink-0 rounded-full"
              personaAvatar={personaAvatar}
            />
            <span
              className="min-w-0 truncate text-base sm:text-lg font-semibold tracking-tight font-serif"
              style={{ color: "var(--theme-text)" }}
            >
              {personaName || t("chat.message.assistant")}
            </span>
          </div>

          {/* Run just started, no parts yet: working row stays, loading icon under the divider */}
          {isStreaming && !hasParts && (
            <RunStepsCollapse
              steps={0}
              durationMs={null}
              startedAtMs={getRunStartedAtMs(message)}
              stateKey={message.id}
              active
              renderExpanded={() => (
                <Loader2
                  size={16}
                  className="animate-spin text-theme-text-tertiary"
                />
              )}
            />
          )}

          {hasParts ? (
            <div className="space-y-3 my-2">
              {(runHeadGroups.length > 0 || message.isStreaming) && (
                <RunStepsCollapse
                  steps={countRunSteps(message.parts!)}
                  durationMs={getRunElapsedMs(message)}
                  startedAtMs={getRunStartedAtMs(message)}
                  stateKey={message.id}
                  active={message.isStreaming}
                  stopped={message.cancelled === true}
                  renderExpanded={() => renderPartGroups(runHeadGroups)}
                />
              )}
              {renderPartGroups(runTailGroups)}
              <RevealArtifactsSummary
                parts={message.parts}
                isStreaming={message.isStreaming}
                onOpenPreview={onOpenPreview}
              />
            </div>
          ) : (
            <>
              {message.content && (
                <MarkdownContent
                  content={message.content}
                  isStreaming={message.isStreaming}
                  headingAnchorContext={{ messageId: message.id, partIndex: 0 }}
                />
              )}
              {message.toolCalls && message.toolCalls.length > 0 && (
                <div className="mt-4 space-y-2">
                  <div
                    className="text-xs font-medium uppercase tracking-wide mb-2"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {t("chat.message.toolCalls")} ({message.toolCalls.length})
                  </div>
                  {message.toolCalls.map((call: ToolCall, index: number) => {
                    const result = message.toolResults?.find(
                      (r: ToolResult) => r.name === call.name,
                    );
                    return (
                      <ToolCallItem
                        key={index}
                        name={call.name}
                        args={call.args || {}}
                        result={result?.result}
                        success={result?.success}
                        isPending={!result && message.isStreaming}
                      />
                    );
                  })}
                </div>
              )}
            </>
          )}
          {/* Streaming state now lives in the RunStepsCollapse "Working…" row (Codex-style) */}
        </div>
        {/* Copy button and Token button - same line at bottom, show on message hover (only after message completes) */}
        {!message.isStreaming && !isWaitingForHuman && (
          <div className="chat-message-actions flex items-center gap-1 pb-2">
            <button
              onClick={() => {
                const textContent = getAssistantTextContent();
                if (textContent) {
                  copyToClipboard(textContent);
                  setCopied(true);
                  toast.success(t("chat.message.copied"));
                  setTimeout(() => setCopied(false), 2000);
                }
              }}
              className={clsx(
                "p-1.5 rounded-md transition-colors",
                copied
                  ? "text-emerald-500 dark:text-emerald-400"
                  : "hover:bg-stone-200 dark:hover:bg-stone-700 text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
              )}
              title={copied ? t("chat.message.copied") : t("chat.message.copy")}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
            {isAuthenticated && sessionId && (
              <BookmarkButton
                sessionId={sessionId}
                messageId={message.id}
                runId={message.runId || runId}
                label={buildBookmarkLabel(getAssistantTextContent())}
              />
            )}
            {sessionId && onForkMessage && (
              <button
                onClick={async () => {
                  if (isForking) return;
                  setIsForking(true);
                  try {
                    await onForkMessage(message.id);
                  } finally {
                    setIsForking(false);
                  }
                }}
                disabled={isForking}
                className={clsx(
                  "p-1.5 rounded-md transition-colors",
                  "hover:bg-stone-200 dark:hover:bg-stone-700",
                  "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
                  isForking && "opacity-60 cursor-wait",
                )}
                title={t("chat.message.fork")}
              >
                {isForking ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <GitBranch size={16} />
                )}
              </button>
            )}
            {/* Token usage statistics button */}
            {(message.tokenUsage || message.duration) && (
              <TokenDetailsButton
                tokenUsage={message.tokenUsage}
                duration={message.duration}
                timestamp={message.timestamp}
                modelDetails={modelDetails}
                fxRates={fxRates}
                language={i18n.language}
              />
            )}
            {showFeedbackAndShareActions && (
              <>
                {/* Feedback buttons */}
                {isAuthenticated && sessionId && (message.runId || runId) && (
                  <FeedbackButtons
                    sessionId={sessionId}
                    runId={message.runId || runId!}
                    currentFeedback={message.feedback}
                  />
                )}
                {/* Share button */}
                {sessionId && (
                  <ShareButton
                    sessionId={sessionId}
                    runId={message.runId || runId}
                  />
                )}
              </>
            )}
            {shouldShowGoalDetailsForMessage(activeGoal, message) && (
              <GoalDetailsButton goal={activeGoal!} />
            )}
          </div>
        )}
        {!message.isStreaming &&
          !isWaitingForHuman &&
          isLastMessage &&
          message.parts?.some((p) => p.type === "recommend_questions") && (
            <div className="space-y-3 my-2">
              {message
                .parts!.filter((p) => p.type === "recommend_questions")
                .map((part, index) => (
                  <MessagePartRenderer
                    key={`rec-${index}`}
                    part={part}
                    messageId={message.id}
                    partIndex={index}
                    isStreaming={false}
                    isLast={false}
                    activePreview={activePreview}
                    onOpenPreview={onOpenPreview}
                    onRecommendQuestionClick={onRecommendQuestionClick}
                    allowAutoPreview={undefined}
                  />
                ))}
            </div>
          )}
      </div>
    </div>
  );
}, areChatMessagePropsEqual);
