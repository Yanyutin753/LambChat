import { clsx } from "clsx";
import { RotateCcw, Square } from "lucide-react";
import type { MessagePart } from "../../../types";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "./MarkdownContent";
import {
  ToolCallItem,
  FileRevealItem,
  ProjectRevealItem,
  ReadFileItem,
  EditFileItem,
  WriteFileItem,
  GrepItem,
  LsItem,
  GlobItem,
  ExecuteItem,
  ImageGenerateItem,
  AudioTranscribeItem,
  ScheduledTaskItem,
  EnvVarItem,
  PersonaItem,
  TeamItem,
  SandboxMcpItem,
  MemoryRecallItem,
  MemoryStoreItem,
  AskHumanItem,
  ToolSearchItem,
} from "./ToolCallItem";
import { ThinkingBlock, SubagentBlock, SandboxItem } from "./SubagentBlocks";
import { TodoBlock } from "./TodoBlock";
import { SummaryItem } from "./SummaryItem";
import type { RevealPreviewRequest } from "./items/revealPreviewData";
import type { RevealPreviewOpenSource } from "./items/revealPreviewState";
import { createToolPartAnchorId } from "./messagePartAnchors";
import {
  getToolRendererId,
  type PluginRuntimeContributionStates,
} from "../../../extensions/coreContributions";

// Render single message part (shared by main agent and subagent)
export function MessagePartRenderer({
  part,
  messageId,
  partIndex,
  isStreaming,
  isLast,
  allowAutoPreview,
  activePreview,
  onOpenPreview,
  onRecommendQuestionClick,
  onRetryCancelled,
  runtimePlugins,
}: {
  part: MessagePart;
  messageId?: string;
  partIndex?: number;
  isStreaming?: boolean;
  isLast: boolean;
  allowAutoPreview?: boolean;
  activePreview?: RevealPreviewRequest | null;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  onRecommendQuestionClick?: (question: string) => void;
  onRetryCancelled?: () => void;
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  const { t } = useTranslation();
  const toolPartAnchorId =
    messageId !== undefined && partIndex !== undefined
      ? createToolPartAnchorId(messageId, partIndex)
      : undefined;

  if (part.type === "text") {
    return (
      <MarkdownContent
        content={part.content}
        isStreaming={isStreaming && isLast}
        headingAnchorContext={
          messageId !== undefined && partIndex !== undefined
            ? {
                messageId,
                partIndex,
              }
            : undefined
        }
      />
    );
  }

  if (part.type === "tool") {
    const coreToolRendererId = getToolRendererId(part.name, runtimePlugins);

    // Detect Read tool, use dedicated component (strips line numbers, shows file path)
    if (coreToolRendererId === "read-file") {
      return (
        <ReadFileItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect reveal_file tool, use dedicated component
    if (coreToolRendererId === "reveal-file") {
      return (
        <div
          id={toolPartAnchorId}
          className="scroll-mt-6 rounded-xl transition-[box-shadow] duration-300 data-[external-navigation-highlighted=true]:ring-2 data-[external-navigation-highlighted=true]:ring-amber-500/80 data-[external-navigation-highlighted=true]:shadow-[0_0_20px_rgba(245,158,11,0.25)] dark:data-[external-navigation-highlighted=true]:ring-amber-400/60 dark:data-[external-navigation-highlighted=true]:shadow-[0_0_20px_rgba(251,191,36,0.12)]"
        >
          <FileRevealItem
            args={part.args}
            result={part.result}
            success={part.success}
            isPending={part.isPending}
            cancelled={part.cancelled}
            allowAutoPreview={allowAutoPreview}
            activePreview={activePreview}
            onOpenPreview={onOpenPreview}
            startedAt={part.startedAt}
            completedAt={part.completedAt}
          />
        </div>
      );
    }
    // Detect reveal_project tool, use dedicated component
    if (coreToolRendererId === "reveal-project") {
      return (
        <div
          id={toolPartAnchorId}
          className="scroll-mt-6 rounded-2xl transition-[box-shadow] duration-300 data-[external-navigation-highlighted=true]:ring-2 data-[external-navigation-highlighted=true]:ring-amber-500/80 data-[external-navigation-highlighted=true]:shadow-[0_0_20px_rgba(245,158,11,0.25)] dark:data-[external-navigation-highlighted=true]:ring-amber-400/60 dark:data-[external-navigation-highlighted=true]:shadow-[0_0_20px_rgba(251,191,36,0.12)]"
        >
          <ProjectRevealItem
            args={part.args}
            result={part.result}
            success={part.success}
            isPending={part.isPending}
            cancelled={part.cancelled}
            allowAutoPreview={allowAutoPreview}
            activePreview={activePreview}
            onOpenPreview={onOpenPreview}
            startedAt={part.startedAt}
            completedAt={part.completedAt}
          />
        </div>
      );
    }
    // Detect edit_file tool, use dedicated component
    if (coreToolRendererId === "edit-file") {
      return (
        <EditFileItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect write_file tool, use dedicated component
    if (coreToolRendererId === "write-file") {
      return (
        <WriteFileItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect grep tool, use dedicated component
    if (coreToolRendererId === "grep") {
      return (
        <GrepItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect ls tool, use dedicated component
    if (coreToolRendererId === "ls") {
      return (
        <LsItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect glob tool, use dedicated component
    if (coreToolRendererId === "glob") {
      return (
        <GlobItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect execute tool, use dedicated component
    if (coreToolRendererId === "execute") {
      return (
        <ExecuteItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect internal MCP tools, use dedicated themed components
    if (coreToolRendererId === "image-generate") {
      return (
        <ImageGenerateItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "audio-transcribe") {
      return (
        <AudioTranscribeItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "scheduled-task") {
      return (
        <ScheduledTaskItem
          toolName={part.name}
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "env-var") {
      return (
        <EnvVarItem
          toolName={part.name}
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "persona") {
      return (
        <PersonaItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "agent-team") {
      return (
        <TeamItem
          toolName={part.name}
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "sandbox-mcp") {
      return (
        <SandboxMcpItem
          toolName={part.name}
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "memory-recall") {
      return (
        <MemoryRecallItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    if (coreToolRendererId === "memory-store") {
      return (
        <MemoryStoreItem
          toolName={part.name}
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect ask_human tool, use dedicated component
    if (coreToolRendererId === "ask-human") {
      return (
        <AskHumanItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    // Detect search_tools, use dedicated component (shows tool discovery results as cards)
    if (coreToolRendererId === "search-tools") {
      return (
        <ToolSearchItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          startedAt={part.startedAt}
          completedAt={part.completedAt}
        />
      );
    }
    return (
      <ToolCallItem
        id={part.id}
        name={part.name}
        args={part.args}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        cancelled={part.cancelled}
        startedAt={part.startedAt}
        completedAt={part.completedAt}
      />
    );
  }

  if (part.type === "thinking") {
    return (
      <ThinkingBlock
        content={part.content}
        isStreaming={isStreaming && isLast && part.isStreaming}
        panelKey={part.thinking_id}
      />
    );
  }

  if (part.type === "subagent") {
    return (
      <SubagentBlock
        agent_id={part.agent_id}
        agent_name={part.agent_name}
        agent_avatar={part.agent_avatar}
        input={part.input}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        parts={part.parts}
        startedAt={part.startedAt}
        completedAt={part.completedAt}
        status={part.status}
        error={part.error}
        runtimePlugins={runtimePlugins}
      />
    );
  }

  // Sandbox status block
  if (part.type === "sandbox") {
    return (
      <SandboxItem
        status={part.status}
        sandboxId={part.sandbox_id}
        error={part.error}
        startedAt={part.startedAt}
        completedAt={part.completedAt}
      />
    );
  }

  // Todo task list block
  if (part.type === "todo") {
    return (
      <TodoBlock
        items={part.items}
        isStreaming={isStreaming && isLast && part.isStreaming}
      />
    );
  }

  // Summary block
  if (part.type === "summary") {
    const panelKey = `summary:${part.agent_id || "root"}:${part.depth || 0}:${
      part.summary_id || "default"
    }`;
    return (
      <SummaryItem
        content={part.content}
        isStreaming={isStreaming && isLast && part.isStreaming}
        panelKey={panelKey}
      />
    );
  }

  if (part.type === "recommend_questions") {
    if (isStreaming) {
      return null;
    }

    return (
      <div className="flex flex-col gap-2.5">
        {part.questions.map((question, index) => (
          <button
            key={`${question.content}-${index}`}
            type="button"
            onClick={() => onRecommendQuestionClick?.(question.content)}
            disabled={!onRecommendQuestionClick}
            className={clsx(
              "mt-1 w-fit rounded-xl ring-1 ring-inset shadow-sm px-3.5 py-2 text-left text-sm leading-snug transition-all duration-200 active:scale-[0.98]",
              "ring-theme-border bg-theme-bg-card text-theme-text-secondary hover:ring-theme-border-hover hover:shadow-[0_2px_8px_-2px_var(--theme-shadow-md)] hover:bg-theme-bg-subtle",
              !onRecommendQuestionClick && "cursor-default opacity-70",
            )}
          >
            {question.content}
          </button>
        ))}
      </div>
    );
  }

  if (part.type === "cancelled") {
    return (
      <div
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-medium"
        style={{
          background:
            "color-mix(in srgb, var(--theme-primary) 8%, transparent)",
          border:
            "1px solid color-mix(in srgb, var(--theme-primary) 18%, transparent)",
          color: "var(--theme-primary)",
        }}
      >
        <Square size={10} fill="currentColor" className="shrink-0" />
        <span>{t("chat.message.interrupted")}</span>
        {onRetryCancelled && (
          <button
            type="button"
            onClick={onRetryCancelled}
            className={clsx(
              "ml-0.5 inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium",
              "bg-white/70 dark:bg-white/[0.07]",
              "border border-white/40 dark:border-white/10",
              "transition-all duration-150 ease-out",
              "hover:bg-white dark:hover:bg-white/12",
              "active:scale-[0.97]",
              "[&>svg]:transition-transform [&>svg]:duration-300",
              "hover:[&>svg]:-rotate-180",
            )}
          >
            <RotateCcw size={11} className="shrink-0" />
            {t("chat.message.retryAnswer")}
          </button>
        )}
      </div>
    );
  }

  return null;
}
