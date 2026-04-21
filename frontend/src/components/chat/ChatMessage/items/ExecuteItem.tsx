import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { Terminal, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";

const ExecuteItem = memo(function ExecuteItem({
  args,
  result,
  success,
  isPending,
  cancelled,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
}) {
  const { t } = useTranslation();
  const command = (args.command as string) || "";
  const timeout = args.timeout as number | undefined;

  const parsed = useMemo(() => {
    if (!result) return { output: "", exitCode: null, truncated: false };
    const raw = extractText(result);

    // Parse the status line appended by deepagents backend
    let exitCode: number | null = null;
    let truncated = false;
    const lines = raw.split("\n");
    const statusLines: string[] = [];

    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (line.match(/^\[Command (succeeded|failed)/)) {
        statusLines.unshift(lines.splice(i, 1)[0]);
        const codeMatch = line.match(/exit code (\d+)/);
        if (codeMatch) exitCode = parseInt(codeMatch[1], 10);
      } else if (line.match(/^\[Output was truncated/)) {
        statusLines.unshift(lines.splice(i, 1)[0]);
        truncated = true;
      } else if (line.startsWith("[")) {
        // Might be a status line from a sub-step, stop parsing
        break;
      } else {
        break;
      }
    }

    return { output: lines.join("\n").trim(), exitCode, truncated };
  }, [result]);

  const canExpand = !!command || !!parsed.output;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-3">
      <div className="px-3 py-2.5 rounded-lg bg-stone-900 dark:bg-stone-950 text-sm font-mono flex items-center gap-2 flex-wrap">
        <span className="text-emerald-400 font-semibold">$</span>
        <span className="text-stone-200 break-all min-w-0">{command}</span>
        {timeout && (
          <span className="shrink-0 px-2 py-0.5 rounded-md bg-stone-700 text-stone-300 text-xs">
            {timeout}s
          </span>
        )}
      </div>

      {parsed.output && (
        <pre
          className={clsx(
            "text-sm rounded-lg p-4 min-w-0",
            "bg-stone-50 dark:bg-stone-900 border border-stone-200/60 dark:border-stone-700/50",
            "text-stone-700 dark:text-stone-300 whitespace-pre-wrap break-words font-mono",
          )}
        >
          {parsed.output}
        </pre>
      )}

      {!isPending && result && (
        <div
          className={clsx(
            "flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg",
            parsed.exitCode === 0
              ? "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30"
              : "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30",
          )}
        >
          {parsed.exitCode === 0 ? (
            <CheckCircle2 size={14} className="shrink-0" />
          ) : (
            <XCircle size={14} className="shrink-0" />
          )}
          <span>
            {parsed.exitCode !== null
              ? t("chat.message.toolExitCode", { code: parsed.exitCode })
              : success
                ? t("chat.message.toolSuccess")
                : t("chat.message.toolFailed")}
          </span>
          {parsed.truncated && (
            <AlertTriangle size={14} className="shrink-0 ml-1 text-amber-500" />
          )}
        </div>
      )}
    </div>
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Terminal size={12} className="shrink-0 opacity-50" />}
        label={
          command
            ? `${t("chat.message.toolExecute")} ${
                command.length > 80 ? command.slice(0, 77) + "…" : command
              }`
            : t("chat.message.toolExecute")
        }
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: t("chat.message.toolExecute"),
            icon: <Terminal size={16} />,
            status,
            subtitle:
              command.length > 120 ? command.slice(0, 117) + "…" : command,
            children: detailContent,
          });
        }}
      >
        {canExpand && (
          <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2 max-h-80 overflow-y-auto min-w-0">
            <div className="px-2 py-1.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-500 dark:text-stone-400 font-mono flex items-center gap-2 flex-wrap">
              <span className="text-stone-700 dark:text-stone-200">$</span>
              <span className="text-emerald-600 dark:text-emerald-400 break-all min-w-0">
                {command}
              </span>
              {timeout && (
                <span className="shrink-0 px-1.5 py-0.5 rounded bg-stone-200 dark:bg-stone-700 text-stone-600 dark:text-stone-300">
                  {timeout}s
                </span>
              )}
            </div>

            {parsed.output && (
              <pre
                className={clsx(
                  "text-xs rounded-md p-2.5 min-w-0",
                  "bg-stone-50 dark:bg-stone-900 border border-stone-200/60 dark:border-stone-700/50",
                  "text-stone-700 dark:text-stone-300 whitespace-pre-wrap break-words font-mono",
                )}
              >
                {parsed.output}
              </pre>
            )}

            {!isPending && result && (
              <div
                className={clsx(
                  "flex items-center gap-1.5 text-xs px-2 py-1 rounded-md",
                  parsed.exitCode === 0
                    ? "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30"
                    : "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30",
                )}
              >
                {parsed.exitCode === 0 ? (
                  <CheckCircle2 size={12} className="shrink-0" />
                ) : (
                  <XCircle size={12} className="shrink-0" />
                )}
                <span>
                  {parsed.exitCode !== null
                    ? t("chat.message.toolExitCode", { code: parsed.exitCode })
                    : success
                      ? t("chat.message.toolSuccess")
                      : t("chat.message.toolFailed")}
                </span>
                {parsed.truncated && (
                  <AlertTriangle
                    size={12}
                    className="shrink-0 ml-1 text-amber-500"
                  />
                )}
              </div>
            )}
          </div>
        )}
      </CollapsiblePill>
    </>
  );
});

export { ExecuteItem };
