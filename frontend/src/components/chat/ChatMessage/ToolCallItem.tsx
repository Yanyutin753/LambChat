import { Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, LoadingSpinner } from "../../common";
import type { CollapsibleStatus } from "../../common";
import { ToolResultContent } from "./items/McpBlockPreview";

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
  const hasResult = result !== undefined;

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

  return (
    <CollapsiblePill
      status={status}
      icon={<Wrench size={12} className="shrink-0 opacity-50" />}
      label={name}
      variant="tool"
      expandable={canExpand}
    >
      {canExpand && (
        <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2 max-h-80 overflow-hidden min-w-0">
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
  );
}
