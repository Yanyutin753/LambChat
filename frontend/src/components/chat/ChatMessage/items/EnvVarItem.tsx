import { memo, useMemo } from "react";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";

function getActionLabel(
  toolName: string,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const map: Record<string, string> = {
    env_var_list: "chat.message.toolEnvVarList",
    env_var_set: "chat.message.toolEnvVarSet",
    env_var_delete: "chat.message.toolEnvVarDelete",
    env_var_delete_all: "chat.message.toolEnvVarDeleteAll",
  };
  return t(map[toolName] || "chat.message.toolEnvVar");
}

const EnvVarItem = memo(function EnvVarItem({
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  toolName: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );

  const actionLabel = getActionLabel(toolName, t);
  const key = (args.key as string) || "";

  const keys = useMemo(() => {
    const text = extractText(result);
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      // env_var_list returns {variables: [{key, masked_value}, ...], count}
      if (parsed?.variables && Array.isArray(parsed.variables)) {
        return parsed.variables
          .map((v: Record<string, unknown>) => v.key)
          .filter(Boolean) as string[];
      }
      // Direct array of keys
      if (Array.isArray(parsed)) {
        return parsed
          .map((item: unknown) =>
            typeof item === "string"
              ? item
              : (item as Record<string, unknown>)?.key ?? String(item),
          )
          .filter(Boolean) as string[];
      }
      if (parsed && typeof parsed === "object" && parsed.keys) {
        return Array.isArray(parsed.keys)
          ? (parsed.keys as string[]).filter(Boolean)
          : [];
      }
      if (parsed && typeof parsed === "object" && parsed.key) {
        return [parsed.key as string];
      }
    } catch {
      // not JSON
    }
    return [];
  }, [result]);

  const allKeys = useMemo(() => {
    const set = new Set<string>();
    if (key) set.add(key);
    keys.forEach((k) => set.add(k));
    return [...set];
  }, [key, keys]);

  const canExpand = allKeys.length > 0 || !!result;
  const pillStatus = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const labelSuffix = key || (allKeys.length > 0 ? `${allKeys.length}` : "");

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {allKeys.length > 0 && (
        <div className="rounded-xl border border-theme-border overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2 px-3 py-2.5 bg-emerald-50/60 dark:bg-emerald-950/20 border-b border-theme-border">
            <ShieldCheck
              size={13}
              className="text-emerald-500 dark:text-emerald-400 shrink-0"
            />
            <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
              {t("chat.message.toolVarCount", { count: allKeys.length })}
            </span>
            <span className="text-[10px] text-emerald-600/60 dark:text-emerald-400/50 ml-auto">
              {t("chat.message.envMasked", "Values masked")}
            </span>
          </div>
          {/* Key list */}
          <div className="divide-y divide-theme-border/40 bg-theme-bg">
            {allKeys.map((k, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 px-3 py-2.5 hover:bg-emerald-50/40 dark:hover:bg-emerald-950/10 transition-colors tool-file-row"
              >
                <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 bg-emerald-100/70 dark:bg-emerald-900/20">
                  <KeyRound
                    size={11}
                    className="text-emerald-500 dark:text-emerald-400"
                  />
                </div>
                <span className="text-sm font-mono text-theme-text truncate flex-1">
                  {k}
                </span>
                <span className="text-[11px] text-theme-text-tertiary font-mono shrink-0 tracking-widest">
                  ••••••••
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result && allKeys.length === 0 && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {(() => {
            const text = extractText(result);
            return text.length > 600 ? text.slice(0, 597) + "…" : text;
          })()}
          <ToolHoverCopyButton
            text={extractText(result)}
            position="result"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </pre>
      )}
    </div>
  );

  // ── Inline (compact) view ──

  return (
    <>
      <CollapsiblePill
        status={pillStatus}
        icon={<KeyRound size={12} className="shrink-0 opacity-50" />}
        label={`${actionLabel}${labelSuffix ? ` ${labelSuffix}` : ""}`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: actionLabel,
            icon: <KeyRound size={16} />,
            status: pillStatus,
            subtitle:
              allKeys.length > 0
                ? t("chat.message.toolVarCount", { count: allKeys.length })
                : undefined,
            children: detailContent,
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {allKeys.length > 0 && (
              <div>
                <div className="text-xs text-theme-text-tertiary mb-1">
                  {t("chat.message.toolVarCount", { count: allKeys.length })}
                </div>
                <div className="flex flex-wrap gap-1">
                  {allKeys.slice(0, 12).map((k, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg border border-theme-border text-[10px] text-theme-text-secondary font-mono hover:border-emerald-200 dark:hover:border-emerald-800/50 transition-colors"
                    >
                      <KeyRound
                        size={9}
                        className="shrink-0 text-emerald-500 dark:text-emerald-400 opacity-70"
                      />
                      {k}
                    </span>
                  ))}
                  {allKeys.length > 12 && (
                    <span className="text-[10px] text-theme-text-tertiary px-1">
                      +{allKeys.length - 12}
                    </span>
                  )}
                </div>
              </div>
            )}

            {result && allKeys.length === 0 && (
              <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
                {(() => {
                  const text = extractText(result);
                  return text.length > 300 ? text.slice(0, 297) + "…" : text;
                })()}
                <ToolHoverCopyButton
                  text={extractText(result)}
                  position="resultCompact"
                />
              </pre>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { EnvVarItem };
