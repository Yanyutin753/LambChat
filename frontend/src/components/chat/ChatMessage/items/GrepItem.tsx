import { memo, useMemo, useState } from "react";
import { Search, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { CodeMirrorViewer } from "../../../common/CodeMirrorViewer";
import { extractText } from "./toolUtils";
import { ToolResultPanel, closeCurrentToolPanel } from "./ToolResultPanel";

const GrepItem = memo(function GrepItem({
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
  const pattern = (args.pattern as string) || "";
  const searchPath = (args.path as string) || "";
  const glob = (args.glob as string) || "";
  const outputMode = (args.output_mode as string) || "files_with_matches";
  const [panelOpen, setPanelOpen] = useState(false);

  const parsedResult = useMemo(() => {
    if (!result) return { files: [] as string[], lines: [] as string[] };
    const raw = extractText(result);
    try {
      const obj = JSON.parse(raw);
      if (Array.isArray(obj)) {
        const files: string[] = [];
        const lines: string[] = [];
        for (const item of obj) {
          if (typeof item === "string") {
            files.push(item);
          } else if (item && typeof item === "object") {
            const file = (item as Record<string, unknown>).file as string;
            if (file) files.push(file);
            const matches = (item as Record<string, unknown>).matches;
            if (Array.isArray(matches)) {
              for (const m of matches) {
                const match = m as Record<string, unknown>;
                lines.push(`${file}:${match.line ?? ""}:${match.text ?? ""}`);
              }
            }
          }
        }
        return { files, lines };
      }
    } catch {
      // 非 JSON，按行解析 ripgrep 风格输出
    }

    const lines: string[] = raw.split("\n").filter(Boolean);
    const files = [
      ...new Set(lines.map((l) => l.split(":")[0]).filter(Boolean)),
    ];
    return { files, lines };
  }, [result]);

  const canExpand =
    !!pattern || parsedResult.files.length > 0 || parsedResult.lines.length > 0;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-3">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-sm text-stone-500 dark:text-stone-400 font-mono flex-wrap">
        <span className="text-violet-600 dark:text-violet-400 font-semibold">
          {pattern}
        </span>
        {searchPath && (
          <span className="text-stone-400 dark:text-stone-500">
            in {searchPath}
          </span>
        )}
        {glob && (
          <span className="shrink-0 px-2 py-0.5 rounded-md bg-stone-200 dark:bg-stone-700 text-stone-600 dark:text-stone-300 text-xs">
            {glob}
          </span>
        )}
      </div>
      {parsedResult.files.length > 0 && (
        <div>
          <div className="text-xs text-stone-400 dark:text-stone-500 mb-2">
            {t("chat.message.toolFileCount", {
              count: parsedResult.files.length,
            })}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {parsedResult.files.slice(0, 20).map((f, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-stone-100 dark:bg-stone-800 text-xs text-stone-600 dark:text-stone-300 font-mono"
              >
                <FileText size={11} className="shrink-0 opacity-40" />
                {f.split("/").pop() || f}
              </span>
            ))}
            {parsedResult.files.length > 20 && (
              <span className="text-xs text-stone-400 dark:text-stone-500 px-1 py-1">
                +{parsedResult.files.length - 20} more
              </span>
            )}
          </div>
        </div>
      )}
      {outputMode === "content" && parsedResult.lines.length > 0 && (
        <div className="rounded-lg border border-stone-200/60 dark:border-stone-700/50 overflow-hidden">
          <CodeMirrorViewer
            value={parsedResult.lines.join("\n")}
            lineNumbers={false}
            maxHeight="60vh"
            fontSize="0.8rem"
          />
        </div>
      )}
      {result &&
        (() => {
          const text = extractText(result);
          return text &&
            parsedResult.lines.length === 0 &&
            parsedResult.files.length === 0 ? (
            <pre className="text-xs text-stone-500 dark:text-stone-400 whitespace-pre-wrap break-words p-3 rounded-lg bg-stone-50 dark:bg-stone-900 border border-stone-200/60 dark:border-stone-700/50">
              {text}
            </pre>
          ) : null;
        })()}
    </div>
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Search size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolSearch")} ${pattern || ""}`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          closeCurrentToolPanel();
          setPanelOpen(true);
        }}
      >
        {canExpand && (
          <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 max-h-80 overflow-y-auto min-w-0">
            <div className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-500 dark:text-stone-400 font-mono flex-wrap">
              <span className="text-violet-600 dark:text-violet-400 font-semibold">
                {pattern}
              </span>
              {searchPath && (
                <span className="text-stone-400 dark:text-stone-500">
                  {t("chat.message.toolInPath", { path: searchPath })}
                </span>
              )}
              {glob && (
                <span className="shrink-0 px-1.5 py-0.5 rounded bg-stone-200 dark:bg-stone-700 text-stone-600 dark:text-stone-300">
                  {glob}
                </span>
              )}
            </div>
            {parsedResult.files.length > 0 && (
              <div className="mb-2">
                <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                  {t("chat.message.toolFileCount", {
                    count: parsedResult.files.length,
                  })}
                </div>
                <div className="flex flex-wrap gap-1">
                  {parsedResult.files.slice(0, 10).map((f, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-600 dark:text-stone-300 font-mono"
                    >
                      <FileText size={10} className="shrink-0 opacity-40" />
                      {f.split("/").pop() || f}
                    </span>
                  ))}
                  {parsedResult.files.length > 10 && (
                    <span className="text-xs text-stone-400 dark:text-stone-500 px-1">
                      {t("chat.message.toolMoreFiles", {
                        count: parsedResult.files.length - 10,
                      })}
                    </span>
                  )}
                </div>
              </div>
            )}
            {outputMode === "content" && parsedResult.lines.length > 0 && (
              <div className="max-h-48 overflow-y-auto rounded-md border border-stone-200/60 dark:border-stone-700/50">
                <CodeMirrorViewer
                  value={parsedResult.lines.slice(0, 50).join("\n")}
                  lineNumbers={false}
                  maxHeight="12rem"
                  fontSize="0.75rem"
                />
                {parsedResult.lines.length > 50 && (
                  <div className="text-stone-400 dark:text-stone-500 mt-1 text-xs px-2 pb-2">
                    {t("chat.message.toolMoreLines", {
                      count: parsedResult.lines.length - 50,
                    })}
                  </div>
                )}
              </div>
            )}
            {result &&
              (() => {
                const text = extractText(result);
                return text &&
                  parsedResult.lines.length === 0 &&
                  parsedResult.files.length === 0 ? (
                  <pre className="text-xs text-stone-500 dark:text-stone-400 whitespace-pre-wrap break-words overflow-y-auto min-w-0">
                    {text}
                  </pre>
                ) : null;
              })()}
          </div>
        )}
      </CollapsiblePill>
      {canExpand && (
        <ToolResultPanel
          open={panelOpen}
          onClose={() => setPanelOpen(false)}
          title={`${t("chat.message.toolSearch")} ${pattern}`}
          icon={<Search size={16} />}
          status={status}
          subtitle={searchPath || glob || undefined}
        >
          {detailContent}
        </ToolResultPanel>
      )}
    </>
  );
});

export { GrepItem };
