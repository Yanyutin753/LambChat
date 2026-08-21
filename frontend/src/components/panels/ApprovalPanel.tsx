import { useState, useEffect, useCallback, useRef } from "react";
import { clsx } from "clsx";
import {
  ShieldCheck,
  X,
  Send,
  ChevronLeft,
  ChevronRight,
  ListOrdered,
  Clock,
  Circle,
  CircleDot,
  Square,
  SquareCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import type { PendingApproval, FormField } from "../../types";
import { ScheduledTaskApprovalContent } from "./ScheduledTaskApprovalContent";
import { Checkbox } from "../common/Checkbox";
import { Input, Select, Textarea } from "../common";
import { cjkGfmRemarkPlugins } from "../common/markdownRemarkPlugins";
import { authFetch } from "../../services/api/fetch";
import { buildApiUrl } from "../../services/api/config";
import { parseDate } from "../../utils/datetime";
import {
  isFormFieldsValid,
  toggleMultiSelectValue,
} from "./approvalFormValidation";

interface ApprovalPanelProps {
  approvals: PendingApproval[];
  onRespond: (
    id: string,
    response: Record<string, unknown>,
    approved: boolean,
  ) => void;
  isLoading: boolean;
}

/** Format seconds into M:SS */
function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function FormFieldRenderer({
  field,
  value,
  onChange,
  disabled,
  onInteract,
}: {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled: boolean;
  onInteract?: () => void;
}) {
  const { t } = useTranslation();
  const cls =
    "w-full rounded-lg pl-3 pr-3 py-2 text-sm transition-all duration-150 focus:outline-none disabled:opacity-50 approval-input";

  const interact = () => onInteract?.();

  const renderChoiceOptions = (multiple = false) => {
    const options = field.options ?? [];
    const selectedValues = Array.isArray(value) ? (value as string[]) : [];
    const selectedValue = typeof value === "string" ? value : "";
    const selectedCount = multiple
      ? selectedValues.length
      : selectedValue
        ? 1
        : 0;

    return (
      <div className="space-y-2">
        <div className="approval-choice-list">
          {options.map((option) => {
            const isSelected = multiple
              ? selectedValues.includes(option)
              : selectedValue === option;
            const Icon = multiple
              ? isSelected
                ? SquareCheck
                : Square
              : isSelected
                ? CircleDot
                : Circle;

            return (
              <button
                key={option}
                type="button"
                onClick={() => {
                  interact();
                  if (multiple) {
                    onChange(
                      isSelected
                        ? selectedValues.filter((v) => v !== option)
                        : [...selectedValues, option],
                    );
                  } else {
                    onChange(option);
                  }
                }}
                disabled={disabled}
                className={clsx(
                  "approval-choice-option",
                  isSelected && "approval-choice-option--selected",
                  disabled && "approval-choice-option--disabled",
                )}
              >
                <Icon size={16} strokeWidth={isSelected ? 2.4 : 1.8} />
                <span>{option}</span>
              </button>
            );
          })}
        </div>
        {multiple && options.length > 0 && (
          <div className="approval-choice-count">
            {selectedCount}/{options.length}
          </div>
        )}
      </div>
    );
  };

  switch (field.type) {
    case "text":
      return (
        <Input
          type="text"
          value={(value as string) ?? ""}
          onChange={(e) => {
            interact();
            onChange(e.target.value);
          }}
          onFocus={interact}
          placeholder={field.placeholder}
          disabled={disabled}
          className={cls}
        />
      );
    case "textarea":
      return (
        <Textarea
          value={(value as string) ?? ""}
          onChange={(e) => {
            interact();
            onChange(e.target.value);
          }}
          onFocus={interact}
          placeholder={field.placeholder}
          disabled={disabled}
          rows={3}
          className={`${cls} resize-none`}
        />
      );
    case "number":
      return (
        <Input
          type="number"
          value={(value as number) ?? ""}
          onChange={(e) => {
            interact();
            onChange(e.target.value ? Number(e.target.value) : "");
          }}
          onFocus={interact}
          placeholder={field.placeholder}
          disabled={disabled}
          className={cls}
        />
      );
    case "checkbox":
      return (
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <Checkbox
            checked={(value as boolean) ?? false}
            onChange={() => {
              interact();
              onChange(!((value as boolean) ?? false));
            }}
            disabled={disabled}
          />
          <span
            className="text-sm transition-colors duration-150 group-hover:text-[var(--theme-text)]"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {field.label}
          </span>
        </label>
      );
    case "select":
      return (
        <Select
          value={(value as string) ?? ""}
          onChange={(v) => {
            interact();
            onChange(v);
          }}
          disabled={disabled}
          className="w-full"
          triggerClassName={cls}
          placeholder={field.placeholder || t("approvals.selectOption")}
          options={[
            ...(field.placeholder
              ? [
                  {
                    value: "",
                    label: field.placeholder,
                    disabled: true,
                  },
                ]
              : []),
            ...(field.options?.map((option) => ({
              value: option,
              label: option,
            })) ?? []),
          ]}
        />
      );
    case "radio":
      return renderChoiceOptions(false);
    case "multi_select": {
      return renderChoiceOptions(true);
    }
    default:
      return null;
  }
}

function AskHumanChoiceList({
  field,
  value,
  disabled,
  selectedIndex,
  onSelect,
  onInteract,
}: {
  field: FormField;
  value: unknown;
  disabled: boolean;
  selectedIndex: number;
  onSelect: (option: string, index: number) => void;
  onInteract: () => void;
}) {
  const { t } = useTranslation();
  const selectedValues = Array.isArray(value) ? (value as string[]) : [];
  const selectedValue = typeof value === "string" ? value : "";
  const isMultiple = field.type === "multi_select";

  return (
    <div className="approval-ask-human-choice-field">
      {isMultiple && (
        <div className="approval-ask-human-multi-select-hint" role="note">
          {t("approvals.multiSelectHint")}
        </div>
      )}
      <div
        className="approval-ask-human-options"
        role="listbox"
        aria-label={field.label}
        aria-multiselectable={isMultiple}
      >
        {(field.options ?? []).map((option, index) => {
          const selected = isMultiple
            ? selectedValues.includes(option)
            : selectedValue === option;
          return (
            <button
              key={option}
              type="button"
              role="option"
              aria-selected={selected}
              disabled={disabled}
              className={clsx(
                "approval-ask-human-option",
                selected && "approval-ask-human-option--selected",
                selectedIndex === index && "approval-ask-human-option--focused",
              )}
              onClick={() => {
                onInteract();
                onSelect(option, index);
              }}
            >
              <span className="approval-ask-human-option-indicator" aria-hidden="true">
                {selected ? "✓" : index + 1}
              </span>
              <span className="min-w-0 flex-1 text-left">{option}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ApprovalPanel({
  approvals,
  onRespond,
  isLoading,
}: ApprovalPanelProps) {
  const { t } = useTranslation();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);
  const [askHumanSelectedIndex, setAskHumanSelectedIndex] = useState(0);
  const [formValues, setFormValues] = useState<
    Record<string, Record<string, unknown>>
  >({});

  // Countdown state: map of approval id -> remaining seconds
  const [remaining, setRemaining] = useState<Record<string, number>>({});
  const currentApprovalId = approvals[currentIndex]?.id;
  // Track expiry deadlines so we can update them on extend
  const deadlinesRef = useRef<Record<string, number>>({});
  // Debounce extend calls (per approval)
  const lastExtendRef = useRef<Record<string, number>>({});
  const EXTEND_COOLDOWN = 30_000; // 30s between extend calls
  const EXTEND_AMOUNT = 60; // extend by 60s
  const DEFAULT_TIMEOUT = 300; // 5min fallback when backend doesn't provide data

  // Initialize deadlines from expires_at / timeout / default
  // 无截止时间审批（interrupt 模式，无 expires_at 且无 timeout）：
  // 不设置倒计时，无限期等待用户响应，也不会自动拒绝
  useEffect(() => {
    const now = Date.now();
    for (const a of approvals) {
      if (a.metadata?.mode === "interrupt") continue;
      if (deadlinesRef.current[a.id]) continue;
      if (!a.expires_at && !a.timeout) continue; // no deadline — wait indefinitely
      let deadline: number;
      let seconds: number;
      if (a.expires_at) {
        deadline = parseDate(a.expires_at).getTime();
        seconds = Math.max(0, Math.floor((deadline - now) / 1000));
      } else {
        const ttl = a.timeout || DEFAULT_TIMEOUT;
        deadline = now + ttl * 1000;
        seconds = ttl;
      }
      deadlinesRef.current[a.id] = deadline;
      setRemaining((prev) => ({
        ...prev,
        [a.id]: seconds,
      }));
    }
    // Clean up removed approvals
    const ids = new Set(
      approvals
        .filter((approval) => approval.metadata?.mode !== "interrupt")
        .map((approval) => approval.id),
    );
    for (const id of Object.keys(deadlinesRef.current)) {
      if (!ids.has(id)) {
        delete deadlinesRef.current[id];
        setRemaining((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }
    }
  }, [approvals]);

  useEffect(() => {
    setAskHumanSelectedIndex(0);
  }, [currentApprovalId]);

  // Countdown tick
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      setRemaining((prev) => {
        const next: Record<string, number> = {};
        let changed = false;
        for (const [id, deadline] of Object.entries(deadlinesRef.current)) {
          const secs = Math.max(
            0,
            Math.floor(((deadline ?? now) - now) / 1000),
          );
          next[id] = secs;
          if (secs !== prev[id]) changed = true;
        }
        return changed ? { ...prev, ...next } : prev;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Auto-close expired approvals
  useEffect(() => {
    for (const a of approvals) {
      const secs = remaining[a.id];
      if (secs === 0 && remaining[a.id] !== undefined) {
        // Expired — auto-reject
        onRespond(a.id, {}, false);
      }
    }
  }, [remaining, approvals, onRespond]);

  // Extend timeout via API
  const extendTimeout = useCallback(async (approvalId: string) => {
    const now = Date.now();
    if (now - (lastExtendRef.current[approvalId] || 0) < EXTEND_COOLDOWN)
      return;
    lastExtendRef.current[approvalId] = now;

    try {
      const res = await authFetch<{
        status: string;
        expires_at: string | null;
      }>(
        buildApiUrl(
          `/human/${approvalId}/extend?extra_seconds=${EXTEND_AMOUNT}`,
        ),
        {
          method: "POST",
        },
      );
      if (res?.status === "success" && res.expires_at) {
        const newDeadline = parseDate(res.expires_at).getTime();
        deadlinesRef.current[approvalId] = newDeadline;
        setRemaining((prev) => ({
          ...prev,
          [approvalId]: Math.max(
            0,
            Math.floor((newDeadline - Date.now()) / 1000),
          ),
        }));
      }
    } catch (err) {
      console.warn("[Approval] Failed to extend timeout:", err);
    }
  }, []);

  // Touch handler — extend on any interaction
  const handleInteract = useCallback(
    (approvalId: string) => () => extendTimeout(approvalId),
    [extendTimeout],
  );

  useEffect(() => {
    setFormValues((prev) => {
      const newValues = { ...prev };
      approvals.forEach((approval) => {
        if (!newValues[approval.id]) {
          const initialValues: Record<string, unknown> = {};
          approval.fields.forEach((field) => {
            initialValues[field.name] =
              field.default ?? getDefaultValue(field.type);
          });
          newValues[approval.id] = initialValues;
        }
      });
      Object.keys(newValues).forEach((id) => {
        if (!approvals.find((a) => a.id === id)) {
          delete newValues[id];
        }
      });
      return newValues;
    });
  }, [approvals]);

  function getDefaultValue(type: FormField["type"]): unknown {
    switch (type) {
      case "text":
      case "textarea":
        return "";
      case "number":
        return 0;
      case "checkbox":
        return false;
      case "select":
      case "radio":
        return "";
      case "multi_select":
        return [];
      default:
        return null;
    }
  }

  useEffect(() => {
    if (currentIndex >= approvals.length) {
      setCurrentIndex(Math.max(0, approvals.length - 1));
    }
  }, [approvals.length, currentIndex]);

  if (approvals.length === 0) return null;

  const safeIndex = Math.min(currentIndex, approvals.length - 1);
  const currentApproval = approvals[safeIndex];

  if (!currentApproval || !currentApproval.message) {
    return null;
  }

  const goToPrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const goToNext = () => {
    setCurrentIndex((prev) => Math.min(approvals.length - 1, prev + 1));
  };

  const currentFormValues = formValues[currentApproval.id] ?? {};
  const currentRemaining = remaining[currentApproval.id];
  const isUrgent = currentRemaining !== undefined && currentRemaining <= 60;
  const approvalSummary = currentApproval.message.replace(/\s+/g, " ").trim();

  const handleFieldChange = (fieldName: string, value: unknown) => {
    setFormValues((prev) => ({
      ...prev,
      [currentApproval.id]: {
        ...(prev[currentApproval.id] ?? {}),
        [fieldName]: value,
      },
    }));
  };

  const handleSubmit = () => {
    if (isAskHuman && !isFormFieldsValid(askHumanFields, currentFormValues)) {
      return;
    }
    onRespond(currentApproval.id, currentFormValues, true);
  };

  const handleCancel = () => {
    onRespond(currentApproval.id, {}, false);
  };

  const isAskHuman = currentApproval.metadata?.mode === "interrupt";
  const askHumanFields = currentApproval.fields;
  const askHumanDisplayFields = askHumanFields.map((field) =>
    field.name === "_other"
      ? {
          ...field,
          label: t("chat.message.askHumanOtherLabel"),
          placeholder:
            field.placeholder || t("chat.message.askHumanOtherPlaceholder"),
        }
      : field,
  );
  const askHumanChoiceFields = askHumanDisplayFields.filter(
    (field) =>
      field.type === "radio" ||
      field.type === "multi_select" ||
      field.type === "select",
  );
  const askHumanKeyboardField = askHumanChoiceFields[0];
  const askHumanQuestion = approvalSummary;
  const isSubmitDisabled =
    isLoading || !isFormFieldsValid(currentApproval.fields, currentFormValues);

  return (
    <div
      className="approval-scroll-container h-full w-full min-h-0 overflow-visible px-2 py-2 sm:px-8 sm:py-3"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      <div className="approval-panel-content-shell mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col lg:max-w-5xl xl:max-w-6xl">
        {/* Pagination */}
        {approvals.length > 1 && (
          <div className="mb-2 flex items-center justify-between px-1">
            <div
              className="flex items-center gap-1.5 text-xs"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              <ListOrdered size={14} />
              <span>
                {currentIndex + 1} / {approvals.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={goToPrev}
                disabled={currentIndex === 0}
                className="p-1.5 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--theme-bg-subtle)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150"
                style={{ color: "var(--theme-text)" }}
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={goToNext}
                disabled={currentIndex === approvals.length - 1}
                className="p-1.5 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--theme-bg-subtle)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150"
                style={{ color: "var(--theme-text)" }}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        <div
          className={`approval-card approval-card--composer ${
            isAskHuman ? "approval-card--ask-human" : ""
          } animate-glass-enter ${
            isExpanded ? "approval-card--expanded" : "approval-card--compact"
          }`}
          key={currentApproval.id}
          onKeyDown={(event) => {
            if (!isAskHuman || !askHumanKeyboardField?.options?.length) return;
            const count = askHumanKeyboardField.options.length;
            if (event.key === "ArrowDown" || event.key === "Tab") {
              event.preventDefault();
              setAskHumanSelectedIndex((index) => (index + 1) % count);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setAskHumanSelectedIndex((index) => (index - 1 + count) % count);
            } else if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              const option =
                askHumanKeyboardField.options[askHumanSelectedIndex];
              if (option) {
                handleFieldChange(
                  askHumanKeyboardField.name,
                  askHumanKeyboardField.type === "multi_select"
                    ? toggleMultiSelectValue(
                        currentFormValues[askHumanKeyboardField.name],
                        option,
                      )
                    : option,
                );
              }
            } else if (
              event.key >= "1" &&
              event.key <= "9" &&
              Number(event.key) <= count
            ) {
              // 数字键快捷选择对应序号的选项
              event.preventDefault();
              const option =
                askHumanKeyboardField.options[Number(event.key) - 1];
              if (option) {
                setAskHumanSelectedIndex(Number(event.key) - 1);
                handleFieldChange(
                  askHumanKeyboardField.name,
                  askHumanKeyboardField.type === "multi_select"
                    ? toggleMultiSelectValue(
                        currentFormValues[askHumanKeyboardField.name],
                        option,
                      )
                    : option,
                );
              }
            }
          }}
          tabIndex={isAskHuman ? 0 : undefined}
        >
          {!isAskHuman ? (
            <button
              type="button"
              className="approval-header approval-compact"
              onClick={() => setIsExpanded((expanded) => !expanded)}
              aria-expanded={isExpanded}
              aria-controls={`approval-details-${currentApproval.id}`}
            >
              <div className="approval-icon">
                <ShieldCheck size={16} strokeWidth={2} />
              </div>
              <div className="min-w-0 flex-1 text-left">
                <span className="approval-title block">
                  {t("approvals.needsConfirmation")}
                </span>
                {!isExpanded && (
                  <span className="approval-summary block">
                    {approvalSummary}
                  </span>
                )}
              </div>
              {currentRemaining !== undefined && (
                <span
                  className={`approval-timer ml-auto flex items-center gap-1 text-xs tabular-nums ${
                    isUrgent ? "approval-timer-urgent" : ""
                  }`}
                >
                  <Clock size={14} />
                  {formatCountdown(currentRemaining)}
                </span>
              )}
              <ChevronRight
                size={16}
                className={`approval-expand-icon shrink-0 transition-transform ${
                  isExpanded ? "rotate-90" : ""
                }`}
                aria-hidden="true"
              />
            </button>
          ) : (
            <div className="approval-ask-human-header">
              <div className="approval-ask-human-title-row">
                <span className="approval-ask-human-badge">
                  {t("approvals.mainGoal")}
                </span>
                <span className="approval-ask-human-question">
                  {askHumanQuestion}
                </span>
              </div>
            </div>
          )}

          {(isExpanded || isAskHuman) && (
            <div id={`approval-details-${currentApproval.id}`}>
              <div className="approval-details-scroll">
              {/* Message */}
              {!isAskHuman && (
                <div className="approval-message">
                  <div
                    className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed prose-p:my-0.5 prose-headings:my-1"
                    style={{ color: "var(--theme-text)" }}
                  >
                    {currentApproval.metadata?.approval_type ===
                      "scheduled_task_create" &&
                    currentApproval.metadata.preview ? (
                      <ScheduledTaskApprovalContent
                        preview={
                          currentApproval.metadata.preview as {
                            name: string;
                            agent_id: string;
                            schedule: string;
                            run_on_start: boolean;
                            timeout_seconds: number;
                            message: string;
                          }
                        }
                      />
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[...cjkGfmRemarkPlugins, remarkBreaks]}
                      >
                        {currentApproval.message}
                      </ReactMarkdown>
                    )}
                  </div>
                </div>
              )}

              {isAskHuman && (
                <div className="approval-form approval-form--ask-human">
                  {askHumanDisplayFields.map((field) => {
                    const isChoice = askHumanChoiceFields.includes(field);
                    return (
                      <div key={field.name} className="space-y-1">
                        <label
                          className="block text-xs font-medium"
                          style={{ color: "var(--theme-text-secondary)" }}
                        >
                          {field.label}
                          {field.required && (
                            <span
                              className="ml-0.5"
                              style={{ color: "#ef4444" }}
                            >
                              *
                            </span>
                          )}
                        </label>
                        {isChoice ? (
                          <AskHumanChoiceList
                            field={field}
                            value={currentFormValues[field.name]}
                            disabled={isLoading}
                            selectedIndex={
                              field === askHumanKeyboardField
                                ? askHumanSelectedIndex
                                : -1
                            }
                            onInteract={handleInteract(currentApproval.id)}
                            onSelect={(option, index) => {
                              if (field === askHumanKeyboardField) {
                                setAskHumanSelectedIndex(index);
                              }
                              handleFieldChange(
                                field.name,
                                field.type === "multi_select"
                                  ? toggleMultiSelectValue(
                                      currentFormValues[field.name],
                                      option,
                                    )
                                  : option,
                              );
                            }}
                          />
                        ) : (
                          <FormFieldRenderer
                            field={field}
                            value={currentFormValues[field.name]}
                            onChange={(value) =>
                              handleFieldChange(field.name, value)
                            }
                            disabled={isLoading}
                            onInteract={handleInteract(currentApproval.id)}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Form fields */}
              {!isAskHuman && currentApproval.fields.length > 0 && (
                <>
                  <div className="approval-divider" />
                  <div className="approval-form space-y-3">
                    {currentApproval.fields
                      .filter((field) => !askHumanChoiceFields.includes(field))
                      .map((field) => {
                        const isOther = field.name === "_other";
                        const displayField = isOther
                          ? {
                              ...field,
                              label: t("chat.message.askHumanOtherLabel"),
                              placeholder:
                                field.placeholder ||
                                t("chat.message.askHumanOtherPlaceholder"),
                            }
                          : field;
                        return (
                          <div key={field.name} className="space-y-1">
                            {displayField.type !== "checkbox" && (
                              <label
                                className="block text-xs font-medium"
                                style={{ color: "var(--theme-text-secondary)" }}
                              >
                                {displayField.label}
                                {displayField.required && (
                                  <span
                                    className="ml-0.5"
                                    style={{ color: "#ef4444" }}
                                  >
                                    *
                                  </span>
                                )}
                              </label>
                            )}
                            <FormFieldRenderer
                              field={displayField}
                              value={currentFormValues[field.name]}
                              onChange={(value) =>
                                handleFieldChange(field.name, value)
                              }
                              disabled={isLoading}
                              onInteract={handleInteract(currentApproval.id)}
                            />
                          </div>
                        );
                      })}
                  </div>
                </>
              )}
              </div>
              <div
                className={`approval-actions ${
                  isAskHuman ? "approval-ask-human-footer" : ""
                }`}
              >
                {isAskHuman && askHumanChoiceFields.length > 0 && (
                  <span
                    className="approval-ask-human-shortcut-hint hidden sm:inline-flex"
                    aria-hidden="true"
                  >
                    {t("approvals.shortcutHint")}
                  </span>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={handleCancel}
                    disabled={isLoading}
                    aria-label={
                      isAskHuman ? t("approvals.ignore") : t("approvals.cancel")
                    }
                    title={
                      isAskHuman ? t("approvals.ignore") : t("approvals.cancel")
                    }
                    className="approval-btn-cancel flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-all duration-200 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <X size={14} />
                    <span>
                      {isAskHuman
                        ? t("approvals.ignore")
                        : t("approvals.cancel")}
                    </span>
                  </button>
                  <button
                    onClick={handleSubmit}
                    disabled={isSubmitDisabled}
                    aria-label={t("approvals.submit")}
                    title={t("approvals.submit")}
                    className="approval-btn-submit flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-all duration-200 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Send size={14} />
                    <span>{t("approvals.submit")}</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
