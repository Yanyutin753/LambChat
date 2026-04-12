import { useState } from "react";
import { Wrench, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, LoadingSpinner } from "../../common";
import type { CollapsibleStatus } from "../../common";
import { ToolResultContent } from "./items/McpBlockPreview";
import {
  ToolResultPanel,
  closeCurrentToolPanel,
} from "./items/ToolResultPanel";

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

// Collapsible Tool Call Item (compact design)
export function ToolCallItem({
  name,
  args,
  result,
  success,
  isPending,
  cancelled,
}: {
  name: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
}) {
  const { t } = useTranslation();
  const [panelOpen, setPanelOpen] = useState(false);
  const hasResult = result !== undefined;

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

  let status: CollapsibleStatus = "idle";
  if (isPending) {
    status = "loading";
  } else if (cancelled) {
    status = "cancelled";
  } else if (success) {
    status = "success";
  } else if (hasResult) {
    status = "error";
  }

  const canExpand = hasArgs || hasResult;

  const panelContent = canExpand && (
    <div className="space-y-3 max-h-[80vh] overflow-y-auto p-1 [&_pre]:!text-sm">
      {hasArgs && (
        <div className="p-3 sm:p-4 rounded-lg bg-stone-50 dark:bg-stone-800/50">
          <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 font-medium">
            {t("chat.message.args")}
          </div>
          <pre className="text-sm text-stone-600 dark:text-stone-300 overflow-x-auto overflow-y-auto min-w-0 font-mono">
            {JSON.stringify(displayArgs, null, 2)}
          </pre>
        </div>
      )}

      {hasResult && (
        <div className="p-3 sm:p-4 rounded-lg bg-stone-50 dark:bg-stone-800/50">
          <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 font-medium">
            {t("chat.message.result")}
          </div>
          <ToolResultContent result={result} />
        </div>
      )}

      {isPending && (
        <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
          <LoadingSpinner size="xs" />
          <span>{t("chat.message.running")}</span>
        </div>
      )}
    </div>
  );

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
        label={toolName}
        suffix={
          serverName ? (
            <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-white/30 dark:bg-black/20 opacity-70 font-medium truncate max-w-[120px]">
              {serverName}
            </span>
          ) : undefined
        }
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          closeCurrentToolPanel();
          setPanelOpen(true);
        }}
      >
        {canExpand && (
          <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2 max-h-96 overflow-y-auto min-w-0">
            {hasArgs && (
              <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
                <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                  {t("chat.message.args")}
                </div>
                <pre className="text-xs text-stone-600 dark:text-stone-300 overflow-x-auto max-h-40 overflow-y-auto min-w-0">
                  {JSON.stringify(displayArgs, null, 2)}
                </pre>
              </div>
            )}

            {hasResult && (
              <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
                <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                  {t("chat.message.result")}
                </div>
                <ToolResultContent result={result} />
              </div>
            )}

            {isPending && (
              <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
                <LoadingSpinner size="xs" />
                <span>{t("chat.message.running")}</span>
              </div>
            )}
          </div>
        )}
      </CollapsiblePill>
      {canExpand && (
        <ToolResultPanel
          open={panelOpen}
          onClose={() => setPanelOpen(false)}
          title={formattedToolName}
          icon={isMcpTool ? <Globe size={16} /> : <Wrench size={16} />}
          status={status}
          subtitle={serverName || undefined}
        >
          {panelContent}
        </ToolResultPanel>
      )}
    </>
  );
}
