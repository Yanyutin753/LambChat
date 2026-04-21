import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { FolderOpen, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractPaths } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";

const LsItem = memo(function LsItem({
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
  const dirPath = (args.path as string) || "/";

  const entries = useMemo(() => {
    return extractPaths(result);
  }, [result]);

  const canExpand = entries.length > 0;
  const displayLabel =
    dirPath === "/" ? "/" : dirPath.split("/").filter(Boolean).pop() || dirPath;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-3">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-sm text-stone-500 dark:text-stone-400 font-mono">
        <FolderOpen size={14} className="shrink-0 opacity-60" />
        <span className="truncate">{dirPath}</span>
        <span className="shrink-0 text-stone-400 dark:text-stone-500">
          {entries.length} items
        </span>
      </div>
      <div className="rounded-lg border border-stone-200/60 dark:border-stone-700/50 bg-stone-50 dark:bg-stone-900 overflow-auto max-h-[60vh]">
        {entries.map((entry, i) => {
          const isDir = entry.endsWith("/") || entry.endsWith("\\");
          const name = isDir
            ? entry.slice(0, -1).split("/").filter(Boolean).pop() ||
              entry.slice(0, -1)
            : entry.split("/").filter(Boolean).pop() || entry;
          return (
            <div
              key={i}
              className={clsx(
                "flex items-center gap-2.5 px-4 py-2 text-sm font-mono",
                "border-b border-stone-100 dark:border-stone-800 last:border-b-0",
                "hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors",
              )}
            >
              {isDir ? (
                <FolderOpen
                  size={14}
                  className="shrink-0 text-amber-500 dark:text-amber-400"
                />
              ) : (
                <FileText
                  size={14}
                  className="shrink-0 text-stone-400 dark:text-stone-500"
                />
              )}
              <span
                className={clsx(
                  "truncate",
                  isDir
                    ? "text-stone-700 dark:text-stone-200 font-medium"
                    : "text-stone-600 dark:text-stone-300",
                )}
              >
                {name}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<FolderOpen size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolLs")} ${displayLabel}`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: `${t("chat.message.toolLs")} ${displayLabel}`,
            icon: <FolderOpen size={16} />,
            status,
            subtitle: dirPath,
            children: detailContent,
          });
        }}
      >
        {canExpand && (
          <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 max-h-80 overflow-y-auto min-w-0">
            <div className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-500 dark:text-stone-400 font-mono">
              <FolderOpen size={12} className="shrink-0 opacity-60" />
              <span className="truncate">{dirPath}</span>
              <span className="shrink-0 text-stone-400 dark:text-stone-500">
                {t("chat.message.toolItemCount", { count: entries.length })}
              </span>
            </div>
            <div className="max-h-48 overflow-y-auto rounded-md border border-stone-200/60 dark:border-stone-700/50 bg-stone-50 dark:bg-stone-900">
              {entries.map((entry, i) => {
                const isDir = entry.endsWith("/") || entry.endsWith("\\");
                const name = isDir
                  ? entry.slice(0, -1).split("/").filter(Boolean).pop() ||
                    entry.slice(0, -1)
                  : entry.split("/").filter(Boolean).pop() || entry;
                return (
                  <div
                    key={i}
                    className={clsx(
                      "flex items-center gap-2 px-3 py-1 text-xs font-mono",
                      "border-b border-stone-100 dark:border-stone-800 last:border-b-0",
                      "hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors",
                    )}
                  >
                    {isDir ? (
                      <FolderOpen
                        size={12}
                        className="shrink-0 text-amber-500 dark:text-amber-400"
                      />
                    ) : (
                      <FileText
                        size={12}
                        className="shrink-0 text-stone-400 dark:text-stone-500"
                      />
                    )}
                    <span
                      className={clsx(
                        "truncate",
                        isDir
                          ? "text-stone-700 dark:text-stone-200 font-medium"
                          : "text-stone-600 dark:text-stone-300",
                      )}
                    >
                      {name}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CollapsiblePill>
    </>
  );
});

export { LsItem };
