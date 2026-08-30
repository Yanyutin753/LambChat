import { memo, useMemo } from "react";
import { clsx } from "clsx";
import {
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Clock,
  Timer,
  Circle,
  CircleDot,
  Square,
  SquareCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { MarkdownContent } from "../MarkdownContent";
import type { FormField } from "../../../../types";

// ── Parsers matching backend ask_human schema ──────────────────────────
// Backend args:  { message: str, fields: FormField[], timeout: int, allow_other: bool }
// Backend result (JSON string): { status: "success"|"timeout"|"rejected", message: str, values: Record<string, unknown> }

interface AskHumanArgs {
  message: string;
  fields: FormField[];
  allow_other?: boolean;
}

interface AskHumanResult {
  status: "success" | "timeout" | "rejected";
  message: string;
  values: Record<string, unknown>;
}

function parseArgs(args: Record<string, unknown>): AskHumanArgs {
  return {
    message: (args.message as string) || "",
    fields: Array.isArray(args.fields) ? (args.fields as FormField[]) : [],
    allow_other: (args.allow_other as boolean) ?? true,
  };
}

function parseResult(
  result: string | Record<string, unknown> | undefined,
): AskHumanResult | null {
  if (!result) return null;
  const text = extractText(result);
  if (!text) return null;
  try {
    const obj = JSON.parse(text);
    if (obj && typeof obj === "object" && typeof obj.status === "string") {
      return {
        status: obj.status,
        message: String(obj.message || ""),
        values:
          obj.values && typeof obj.values === "object"
            ? (obj.values as Record<string, unknown>)
            : {},
      };
    }
  } catch {
    // not JSON
  }
  return null;
}

// ── Read-only field renderer (mirrors ApprovalPanel's FormFieldRenderer) ──

function FieldDisplay({ field, value }: { field: FormField; value: unknown }) {
  const displayValue = (() => {
    if (value === undefined || value === null || value === "") return null;
    if (field.type === "checkbox") return value ? "✓" : "✗";
    if (field.type === "multi_select" && Array.isArray(value))
      return (value as string[]).join(", ");
    return String(value);
  })();

  // select / radio / multi_select -> choice summary
  if (
    (field.type === "select" ||
      field.type === "radio" ||
      field.type === "multi_select") &&
    field.options
  ) {
    const selected: string[] =
      field.type === "multi_select" && Array.isArray(value)
        ? (value as string[])
        : value
          ? [String(value)]
          : [];
    return (
      <div className="space-y-1.5">
        <label
          className="block text-xs font-medium"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {field.label}
          {field.required && (
            <span className="ml-0.5" style={{ color: "#ef4444" }}>
              *
            </span>
          )}
        </label>
        <div className="approval-choice-list approval-choice-list--readonly">
          {field.options.map((option) => {
            const isSelected = selected.includes(option);
            const Icon =
              field.type === "multi_select"
                ? isSelected
                  ? SquareCheck
                  : Square
                : isSelected
                  ? CircleDot
                  : Circle;
            return (
              <span
                key={option}
                className={clsx(
                  "approval-choice-option approval-choice-option--readonly",
                  isSelected && "approval-choice-option--selected",
                  !isSelected && "approval-choice-option--dimmed",
                )}
              >
                <Icon size={15} strokeWidth={isSelected ? 2.4 : 1.8} />
                {option}
              </span>
            );
          })}
        </div>
      </div>
    );
  }

  // checkbox
  if (field.type === "checkbox") {
    const checked = !!value;
    return (
      <div className="flex items-center gap-2.5">
        <div
          className={clsx(
            "w-4 h-4 rounded flex items-center justify-center border-2 transition-colors",
            checked
              ? "bg-[var(--theme-primary)] border-[var(--theme-primary)]"
              : "border-[var(--theme-border)] bg-[var(--theme-bg)]",
          )}
        >
          {checked && (
            <svg
              viewBox="0 0 12 12"
              className="w-2.5 h-2.5 text-white"
              fill="none"
              stroke="currentColor"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2.5 6l2.5 2.5 4.5-5" />
            </svg>
          )}
        </div>
        <span
          className="text-sm"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {field.label}
        </span>
      </div>
    );
  }

  // text / textarea / number
  return (
    <div className="space-y-1">
      <label
        className="block text-xs font-medium"
        style={{ color: "var(--theme-text-secondary)" }}
      >
        {field.label}
        {field.required && (
          <span className="ml-0.5" style={{ color: "#ef4444" }}>
            *
          </span>
        )}
      </label>
      {displayValue !== null ? (
        <div
          className="approval-input approval-answer-filled px-3 py-2 text-sm rounded-lg min-h-[2.25rem] whitespace-pre-wrap break-words"
          style={{ color: "var(--theme-text)" }}
        >
          {displayValue}
        </div>
      ) : (
        <div
          className="approval-input px-3 py-2 text-sm rounded-lg min-h-[2.25rem]"
          style={{ color: "var(--theme-text-dim)", opacity: 0.5 }}
        >
          {field.placeholder || "—"}
        </div>
      )}
    </div>
  );
}

// ── Answer Summary (replaces generic "用户已响应" footer) ──────────────

function AnswerSummary({
  fields,
  values,
  t,
}: {
  fields: FormField[];
  values: Record<string, unknown>;
  t: (key: string) => string;
}) {
  const answeredFields = fields.filter((f) => {
    const v = values[f.name] ?? f.default ?? null;
    if (v === null || v === undefined || v === "") return false;
    if (f.type === "multi_select" && Array.isArray(v) && v.length === 0)
      return false;
    return true;
  });

  if (answeredFields.length === 0) return null;

  const formatValue = (field: FormField, value: unknown): string => {
    if (field.type === "multi_select" && Array.isArray(value))
      return (value as string[]).join(
        t("chat.message.toolAskHumanListSeparator"),
      );
    if (field.type === "checkbox") return value ? "✓" : "✗";
    return String(value);
  };

  return (
    <div className="approval-answer-summary">
      <div className="approval-answer-summary-header">
        <CheckCircle2 size={13} />
        <span>{t("chat.message.askHumanYourAnswer")}</span>
      </div>
      <div className="approval-answer-summary-body">
        {answeredFields.map((field, idx) => {
          const v = values[field.name] ?? field.default ?? null;
          return (
            <div key={field.name} className="approval-answer-item">
              {idx > 0 && <div className="approval-answer-item-sep" />}
              <div className="approval-answer-row">
                <span className="approval-answer-label">{field.label}</span>
                <span className="approval-answer-value">
                  <span className="approval-answer-value-dot" />
                  {formatValue(field, v)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── AskHumanDetail ────────────────────────────────────────────────────

/**
 * 面板详情：实时跟随 toolCallPanelStore 数据重建（用户作答后即时刷新）。
 * 模块作用域声明保证组件类型稳定，流式更新只 patch props，
 * 不会重置内部本地状态（FieldDisplay 等只读展示，无表单输入）。
 */
function AskHumanDetail({
  args,
  result,
  isPending,
}: ToolDetailProps) {
  const { t } = useTranslation();

  const parsed = useMemo(() => parseArgs(args), [args]);
  const parsedResult = useMemo(() => parseResult(result), [result]);

  const { message, fields } = parsed;

  // Supplement _other field when backend didn't include it
  // (e.g. cached events before the backend fix, or non-standard flows).
  const effectiveFields = useMemo(() => {
    const needOther = parsed.allow_other || !!parsedResult?.values?._other;
    if (!needOther) return fields;
    if (fields.some((f) => f.name === "_other")) return fields;
    return [
      ...fields,
      {
        name: "_other",
        label: t("chat.message.askHumanOtherLabel"),
        type: "textarea" as const,
        required: false,
        placeholder: t("chat.message.askHumanOtherPlaceholder"),
      },
    ];
  }, [parsed.allow_other, parsedResult?.values?._other, fields, t]);

  // Resolve i18n for system fields (e.g. _other label from backend)
  const resolvedFields = useMemo(
    () =>
      effectiveFields.map((f) =>
        f.name === "_other"
          ? {
              ...f,
              label: t("chat.message.askHumanOtherLabel"),
              placeholder:
                f.placeholder || t("chat.message.askHumanOtherPlaceholder"),
            }
          : f,
      ),
    [effectiveFields, t],
  );

  const hasFields = effectiveFields.length > 0;

  return (
    <div className="p-4 sm:p-5 space-y-3">
      {/* Mini approval-style card (read-only snapshot) */}
      <div className="approval-card">
        {/* Header */}
        <div className="approval-header">
          <div className="approval-icon">
            <ShieldCheck size={16} strokeWidth={2} />
          </div>
          <span className="approval-title">
            {t("chat.message.toolAskHuman")}
          </span>
          {!isPending && parsedResult && (
            <span
              className={clsx(
                "ml-auto flex items-center gap-1 text-xs font-medium",
                parsedResult.status === "success"
                  ? "text-emerald-600 dark:text-emerald-400"
                  : parsedResult.status === "timeout"
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-red-500 dark:text-red-400",
              )}
            >
              {parsedResult.status === "success" ? (
                <CheckCircle2 size={14} />
              ) : parsedResult.status === "timeout" ? (
                <Timer size={14} />
              ) : (
                <XCircle size={14} />
              )}
              {parsedResult.status === "success"
                ? t("chat.message.askHumanApproved")
                : parsedResult.status === "timeout"
                  ? t("chat.message.askHumanTimeout")
                  : t("chat.message.askHumanRejected")}
            </span>
          )}
          {isPending && (
            <span className="approval-timer ml-auto flex items-center gap-1 text-xs">
              <Clock size={14} className="animate-pulse" />
              {t("chat.message.askHumanWaiting")}
            </span>
          )}
        </div>

        {/* Message (supports markdown) */}
        {message && (
          <div className="approval-message">
            <div
              className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed prose-p:my-0.5 prose-headings:my-1"
              style={{ color: "var(--theme-text)" }}
            >
              <MarkdownContent content={message} />
            </div>
          </div>
        )}

        {/* Form fields (read-only) */}
        {hasFields && (
          <>
            <div className="approval-divider" />
            <div className="approval-form space-y-3">
              {resolvedFields.map((field) => (
                <FieldDisplay
                  key={field.name}
                  field={field}
                  value={
                    parsedResult?.values?.[field.name] ?? field.default ?? null
                  }
                />
              ))}
            </div>
          </>
        )}

        {/* Result summary — structured answer display */}
        {!isPending && parsedResult && parsedResult.status === "success" && (
          <>
            <div className="approval-divider" />
            <div className="approval-result-section">
              <AnswerSummary
                fields={resolvedFields}
                values={parsedResult.values}
                t={t}
              />
            </div>
          </>
        )}

        {/* Result message for non-success states */}
        {!isPending &&
          parsedResult?.message &&
          parsedResult.status !== "success" && (
            <>
              <div className="approval-divider" />
              <div className="approval-result-section">
                <div
                  className={clsx(
                    "text-xs px-3 py-2 rounded-lg",
                    parsedResult.status === "timeout"
                      ? "bg-amber-50 dark:bg-amber-950/25 text-amber-700 dark:text-amber-300"
                      : "bg-red-50 dark:bg-red-950/25 text-red-600 dark:text-red-400",
                  )}
                >
                  {parsedResult.message}
                </div>
              </div>
            </>
          )}
      </div>

      {/* Raw result fallback (when no structured result) */}
      {result && !parsedResult && (
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
}

// ── AskHumanItem ──────────────────────────────────────────────────────

const AskHumanItem = memo(function AskHumanItem({
  id,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
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

  const parsed = useMemo(() => parseArgs(args), [args]);
  const parsedResult = useMemo(() => parseResult(result), [result]);

  const { message, fields } = parsed;

  // Supplement _other field when backend didn't include it
  // (e.g. cached events before the backend fix, or non-standard flows).
  const effectiveFields = useMemo(() => {
    const needOther = parsed.allow_other || !!parsedResult?.values?._other;
    if (!needOther) return fields;
    if (fields.some((f) => f.name === "_other")) return fields;
    return [
      ...fields,
      {
        name: "_other",
        label: t("chat.message.askHumanOtherLabel"),
        type: "textarea" as const,
        required: false,
        placeholder: t("chat.message.askHumanOtherPlaceholder"),
      },
    ];
  }, [parsed.allow_other, parsedResult?.values?._other, fields, t]);

  const hasFields = effectiveFields.length > 0;
  const canExpand = !!message || hasFields || !!result;

  // Derive pill status
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : parsedResult?.status === "rejected"
        ? "cancelled"
        : parsedResult?.status === "timeout"
          ? "error"
          : success
            ? "success"
            : "error";

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <AskHumanDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  // ── Label ──

  const labelText = (() => {
    const base = t("chat.message.toolAskHuman");
    if (message) {
      const preview =
        message.length > 50 ? message.slice(0, 47) + "…" : message;
      // Strip markdown for pill label
      const plain = preview.replace(/[#*_`~>[\]!]/g, "").trim();
      return `${base} — ${plain}`;
    }
    return base;
  })();

  // ── Inline (compact) content ──

  const compactContent = canExpand && (
    <ToolInlineDetails>
      {/* Message summary */}
      {message && (
        <div className="flex items-start gap-2 px-2.5 py-2 rounded-lg bg-theme-bg border border-theme-border">
          <ShieldCheck
            size={12}
            className="shrink-0 mt-0.5 text-[#f59e0b] dark:text-[#fbbf24]"
          />
          <span className="text-xs text-theme-text leading-relaxed line-clamp-2">
            {message.length > 200 ? message.slice(0, 197) + "…" : message}
          </span>
        </div>
      )}

      {/* Fields count badges */}
      {hasFields && (
        <div className="flex flex-wrap gap-1">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-10 font-medium bg-[#fef3c7] dark:bg-[#451a03] text-amber-700 dark:text-amber-300 ring-1 ring-inset ring-amber-200/50 dark:ring-amber-800/30">
            {t("chat.message.toolAskHumanFieldCount", {
              count: effectiveFields.length,
            })}
          </span>
        </div>
      )}

      {/* Status badge after completion */}
      {!isPending && parsedResult && (
        <div
          className={clsx(
            "flex items-center gap-1.5 px-2 py-1 rounded-md text-11 font-medium",
            parsedResult.status === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/25 text-emerald-600 dark:text-emerald-400"
              : parsedResult.status === "timeout"
                ? "bg-amber-50 dark:bg-amber-950/25 text-amber-600 dark:text-amber-400"
                : "bg-red-50 dark:bg-red-950/25 text-red-500 dark:text-red-400",
          )}
        >
          {parsedResult.status === "success" ? (
            <CheckCircle2 size={10} />
          ) : parsedResult.status === "timeout" ? (
            <Timer size={10} />
          ) : (
            <XCircle size={10} />
          )}
          {parsedResult.status === "success"
            ? t("chat.message.askHumanApproved")
            : parsedResult.status === "timeout"
              ? t("chat.message.askHumanTimeout")
              : t("chat.message.askHumanRejected")}
        </div>
      )}

      {/* Waiting state */}
      {isPending && (
        <div className="flex items-center gap-1.5 text-10 text-amber-600 dark:text-amber-400 px-1">
          <Clock size={10} className="animate-pulse" />
          <span>{t("chat.message.askHumanWaiting")}</span>
        </div>
      )}

      {/* Raw fallback */}
      {result && !parsedResult && (
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
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<ShieldCheck size={12} className="shrink-0 opacity-50" />}
        label={labelText}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolAskHuman"),
            icon: <ShieldCheck size={16} />,
            status,
            subtitle:
              message && message.length > 120
                ? message.slice(0, 117) + "…"
                : message || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <AskHumanDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {compactContent}
      </CollapsiblePill>
    </>
  );
});

export { AskHumanItem };
