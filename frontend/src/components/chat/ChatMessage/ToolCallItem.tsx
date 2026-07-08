import { Globe, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, CopyButton, LoadingSpinner } from "../../common";
import type { CollapsibleStatus } from "../../common";
import { ToolArgsDisplay } from "./ToolArgsDisplay";
import { ToolResultContent } from "./items/McpBlockPreview";
import { ToolDurationFooter } from "./items/ToolDurationFooter";
import { CollapsibleSection } from "./SubagentBlocks";
import {
  openPersistentToolPanel,
  updatePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "./items/persistentToolPanelState";
import {
  toolCallPanelStore,
  type ToolCallPanelData,
} from "./toolCallPanelStore";

/** Returns the number of seconds elapsed since the tool started, or 0 when not pending. */
function useElapsedSeconds(isPending?: boolean, startedAt?: string): number {
  const [elapsed, setElapsed] = useState(0);
  const startTimeMs = useRef<number | null>(null);
  const raf = useRef<number>(0);

  useEffect(() => {
    if (isPending) {
      // Use the tool's actual start time from the backend, fall back to now
      startTimeMs.current = startedAt
        ? new Date(startedAt).getTime()
        : Date.now();
      setElapsed(0);
      const tick = () => {
        if (startTimeMs.current !== null) {
          setElapsed(Math.floor((Date.now() - startTimeMs.current) / 1000));
          raf.current = requestAnimationFrame(tick);
        }
      };
      raf.current = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(raf.current);
    } else {
      startTimeMs.current = null;
      setElapsed(0);
      return () => cancelAnimationFrame(raf.current);
    }
  }, [isPending, startedAt]);

  return elapsed;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function compactPreviewText(
  value: unknown,
  maxLength = 72,
): string | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const raw = typeof value === "string" ? value : JSON.stringify(value);
  const compact = (raw || String(value)).replace(/\s+/g, " ").trim();
  if (!compact) return undefined;
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength - 1)}…`;
}

function buildToolPillSummary(
  args: Record<string, unknown>,
): string | undefined {
  const priorityKeys = [
    "command",
    "path",
    "file_path",
    "query",
    "pattern",
    "code",
    "script",
    "input",
    "prompt",
    "url",
  ];

  for (const key of priorityKeys) {
    const preview = compactPreviewText(args[key]);
    if (preview) return preview;
  }

  const entries = Object.entries(args)
    .map(([key, value]) => {
      const preview = compactPreviewText(value, 36);
      return preview ? `${key}=${preview}` : undefined;
    })
    .filter((entry): entry is string => Boolean(entry))
    .slice(0, 2);

  return entries.length > 0 ? entries.join(" ") : undefined;
}

// Re-export all sub-components
export { ReadFileItem } from "./items/ReadFileItem";
export { EditFileItem } from "./items/EditFileItem";
export { WriteFileItem } from "./items/WriteFileItem";
export { GrepItem } from "./items/GrepItem";
export { LsItem } from "./items/LsItem";
export { GlobItem } from "./items/GlobItem";
export { ExecuteItem } from "./items/ExecuteItem";
export { FileRevealItem } from "./items/FileRevealItem";
export { ProjectRevealItem } from "./items/ProjectRevealItem";
export { ImageGenerateItem } from "./items/ImageGenerateItem";
export { ImageAnalyzeItem } from "./items/ImageAnalyzeItem";
export { AudioTranscribeItem } from "./items/AudioTranscribeItem";
export { UploadUrlToSandboxItem } from "./items/UploadUrlToSandboxItem";
export { TransferItem } from "./items/TransferItem";
export { ScheduledTaskItem } from "./items/ScheduledTaskItem";
export { EnvVarItem } from "./items/EnvVarItem";
export { PersonaItem } from "./items/PersonaItem";
export { TeamItem } from "./items/TeamItem";
export { SandboxMcpItem } from "./items/SandboxMcpItem";
export { MemoryRecallItem } from "./items/MemoryRecallItem";
export { MemoryStoreItem } from "./items/MemoryStoreItem";
export { AskHumanItem } from "./items/AskHumanItem";
export { ToolSearchItem } from "./items/ToolSearchItem";
export { EvalItem } from "./items/EvalItem";

/** Derive status from tool props */
function deriveStatus(props: {
  isPending?: boolean;
  cancelled?: boolean;
  success?: boolean;
  hasResult: boolean;
}): CollapsibleStatus {
  if (props.isPending) return "loading";
  if (props.cancelled) return "cancelled";
  if (props.success) return "success";
  if (props.hasResult) return "error";
  return "idle";
}

// ==========================================
// Tool call panel content (reactive)
// ==========================================

function ToolCallPanelContent({ toolCallId }: { toolCallId: string }) {
  const { t } = useTranslation();
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((n) => n + 1);
    return toolCallPanelStore.subscribe(toolCallId, listener);
  }, [toolCallId]);

  const data = toolCallPanelStore.get(toolCallId);
  const elapsedSeconds = useElapsedSecondsForPanel(
    data?.isPending,
    data?.startedAt,
  );

  if (!data) return null;
  const hasArgs = Object.keys(data.args).length > 0;

  return (
    <div className="space-y-3 max-h-full overflow-y-auto p-2 sm:p-4 [&_pre]:!text-sm">
      {hasArgs && (
        <CollapsibleSection title={t("chat.message.args")}>
          <ToolArgsDisplay args={data.args} />
        </CollapsibleSection>
      )}

      {data.result !== undefined && (
        <CollapsibleSection
          title={t("chat.message.result")}
          action={
            <CopyButton
              text={
                typeof data.result === "string"
                  ? data.result
                  : JSON.stringify(data.result, null, 2)
              }
              size={12}
            />
          }
        >
          <ToolResultContent result={data.result} hideCopyButton />
        </CollapsibleSection>
      )}

      {data.isPending && (
        <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
          <LoadingSpinner size="xs" />
          <span>{t("chat.message.running")}</span>
          <span className="tabular-nums">{formatElapsed(elapsedSeconds)}</span>
        </div>
      )}
    </div>
  );
}

/** Standalone elapsed timer for the reactive panel content */
function useElapsedSecondsForPanel(
  isPending: boolean | undefined,
  startedAt: string | undefined,
): number {
  const [elapsed, setElapsed] = useState(0);
  const startTimeMs = useRef<number | null>(null);
  const raf = useRef<number>(0);

  useEffect(() => {
    if (isPending) {
      startTimeMs.current = startedAt
        ? new Date(startedAt).getTime()
        : Date.now();
      setElapsed(0);
      const tick = () => {
        if (startTimeMs.current !== null) {
          setElapsed(Math.floor((Date.now() - startTimeMs.current) / 1000));
          raf.current = requestAnimationFrame(tick);
        }
      };
      raf.current = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(raf.current);
    } else {
      startTimeMs.current = null;
      setElapsed(0);
      return () => cancelAnimationFrame(raf.current);
    }
  }, [isPending, startedAt]);

  return elapsed;
}

// ==========================================
// Collapsible Tool Call Item
// ==========================================

// Collapsible Tool Call Item (compact design)
export function ToolCallItem({
  id,
  name,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
  name: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const hasResult = result !== undefined;
  const elapsedSeconds = useElapsedSeconds(isPending, startedAt);
  const durationFooter = useMemo(
    () => (
      <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
    ),
    [startedAt, completedAt],
  );

  // Parse MCP server name from tool name (format: "server_name:tool_name")
  const colonIdx = name.indexOf(":");
  const isMcpTool = colonIdx > 0;
  const serverName = isMcpTool ? name.substring(0, colonIdx) : null;
  const toolName = isMcpTool ? name.substring(colonIdx + 1) : name;
  const formattedToolName = toolName
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");

  const displayArgs = (() => {
    if (args.partial !== undefined) {
      try {
        return JSON.parse(args.partial as string);
      } catch {
        return { partial: args.partial };
      }
    }
    return args;
  })();

  const hasArgs = Object.keys(displayArgs).length > 0;

  const status = deriveStatus({ isPending, cancelled, success, hasResult });

  const canExpand = hasArgs || hasResult;
  const pillSummary = buildToolPillSummary(displayArgs);
  const pillLabel = pillSummary ? `${toolName} ${pillSummary}` : toolName;

  // Build a panelKey from the tool call ID (used for persistent panel identity)
  const panelKey = useMemo(() => (id ? `tool:${id}` : undefined), [id]);

  // Sync live data to the reactive store so the persistent panel can read it
  const storeData = useMemo<ToolCallPanelData | null>(
    () =>
      id
        ? {
            toolCallId: id,
            toolName,
            formattedToolName,
            args: displayArgs,
            result,
            success,
            isPending,
            cancelled,
            startedAt,
            completedAt,
            status,
          }
        : null,
    [
      id,
      toolName,
      formattedToolName,
      displayArgs,
      result,
      success,
      isPending,
      cancelled,
      startedAt,
      completedAt,
      status,
    ],
  );

  useEffect(() => {
    if (!storeData) return;
    toolCallPanelStore.set(storeData);
    return () => {
      toolCallPanelStore.delete(storeData.toolCallId);
    };
  }, [storeData]);

  // If a panel is already open for this tool, update its status + footer reactively
  useEffect(() => {
    if (!panelKey || !isPersistentToolPanelOpen(panelKey)) return;
    updatePersistentToolPanel(
      (prev) => ({
        ...prev,
        status,
        footer: durationFooter,
      }),
      panelKey,
    );
  }, [panelKey, status, durationFooter]);

  // Inline content for desktop expand
  const inlineContent = canExpand && (
    <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2 max-h-96 overflow-y-auto min-w-0">
      {hasArgs && (
        <CollapsibleSection title={t("chat.message.args")}>
          <ToolArgsDisplay args={displayArgs} compact />
        </CollapsibleSection>
      )}

      {hasResult && (
        <CollapsibleSection
          title={t("chat.message.result")}
          action={
            <CopyButton
              text={
                typeof result === "string"
                  ? result
                  : JSON.stringify(result, null, 2)
              }
              size={10}
            />
          }
        >
          <ToolResultContent result={result} hideCopyButton />
        </CollapsibleSection>
      )}

      {isPending && (
        <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
          <LoadingSpinner size="xs" />
          <span>{t("chat.message.running")}</span>
          <span className="tabular-nums">{formatElapsed(elapsedSeconds)}</span>
        </div>
      )}
    </div>
  );

  const handlePanelOpen = () => {
    if (!canExpand || !id) return;
    openPersistentToolPanel({
      title: formattedToolName,
      icon: isMcpTool ? <Globe size={16} /> : <Wrench size={16} />,
      status,
      panelKey,
      subtitle: serverName || undefined,
      children: <ToolCallPanelContent toolCallId={id} />,
      footer: durationFooter,
    });
  };

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={
          isMcpTool ? (
            <Globe size={12} className="shrink-0 opacity-50" />
          ) : (
            <Wrench size={12} className="shrink-0 opacity-50" />
          )
        }
        label={pillLabel}
        suffix={
          serverName ? (
            <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-white/30 dark:bg-black/20 opacity-70 font-medium truncate max-w-[120px]">
              {serverName}
            </span>
          ) : undefined
        }
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={handlePanelOpen}
      >
        {inlineContent}
      </CollapsiblePill>
    </>
  );
}
