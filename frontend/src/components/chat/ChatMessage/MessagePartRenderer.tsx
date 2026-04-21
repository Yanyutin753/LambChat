import { clsx } from "clsx";
import { Ban } from "lucide-react";
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
} from "./ToolCallItem";
import { ThinkingBlock, SubagentBlock, SandboxItem } from "./SubagentBlocks";
import { TodoBlock } from "./TodoBlock";
import { SummaryItem } from "./SummaryItem";
import type { RevealPreviewRequest } from "./items/revealPreviewData";
import type { RevealPreviewOpenSource } from "./items/revealPreviewState";

// Render single message part (shared by main agent and subagent)
export function MessagePartRenderer({
  part,
  isStreaming,
  isLast,
  allowAutoPreview,
  activePreview,
  onOpenPreview,
}: {
  part: MessagePart;
  isStreaming?: boolean;
  isLast: boolean;
  allowAutoPreview?: boolean;
  activePreview?: RevealPreviewRequest | null;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
}) {
  const { t } = useTranslation();

  if (part.type === "text") {
    return (
      <MarkdownContent
        content={part.content}
        isStreaming={isStreaming && isLast}
      />
    );
  }

  if (part.type === "tool") {
    // Detect Read tool, use dedicated component (strips line numbers, shows file path)
    if (part.name === "read_file") {
      return (
        <ReadFileItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    // Detect reveal_file tool, use dedicated component
    if (part.name === "reveal_file") {
      return (
        <FileRevealItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          allowAutoPreview={allowAutoPreview}
          activePreview={activePreview}
          onOpenPreview={onOpenPreview}
        />
      );
    }
    // Detect reveal_project tool, use dedicated component
    if (part.name === "reveal_project") {
      return (
        <ProjectRevealItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
          allowAutoPreview={allowAutoPreview}
          activePreview={activePreview}
          onOpenPreview={onOpenPreview}
        />
      );
    }
    // Detect edit_file tool, use dedicated component
    if (part.name === "edit_file") {
      return (
        <EditFileItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    // Detect write_file tool, use dedicated component
    if (part.name === "write_file") {
      return (
        <WriteFileItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    // Detect grep tool, use dedicated component
    if (part.name === "grep") {
      return (
        <GrepItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    // Detect ls tool, use dedicated component
    if (part.name === "ls") {
      return (
        <LsItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    // Detect glob tool, use dedicated component
    if (part.name === "glob") {
      return (
        <GlobItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    // Detect execute tool, use dedicated component
    if (part.name === "execute") {
      return (
        <ExecuteItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
          cancelled={part.cancelled}
        />
      );
    }
    return (
      <ToolCallItem
        name={part.name}
        args={part.args}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        cancelled={part.cancelled}
      />
    );
  }

  if (part.type === "thinking") {
    return (
      <ThinkingBlock
        content={part.content}
        isStreaming={isStreaming && isLast && part.isStreaming}
      />
    );
  }

  if (part.type === "subagent") {
    return (
      <SubagentBlock
        agent_id={part.agent_id}
        agent_name={part.agent_name}
        input={part.input}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        parts={part.parts}
        startedAt={part.startedAt}
        completedAt={part.completedAt}
        status={part.status}
        error={part.error}
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

  if (part.type === "cancelled") {
    return (
      <div
        className={clsx(
          "flex items-center gap-2 px-4 py-2.5 rounded-xl",
          "bg-amber-50 dark:bg-amber-950/40",
          "border border-amber-200/60 dark:border-amber-800/60",
          "text-amber-700 dark:text-amber-400",
          "text-sm font-medium",
        )}
      >
        <Ban size={16} className="shrink-0" />
        <span>{t("chat.message.cancelled")}</span>
      </div>
    );
  }

  return null;
}
