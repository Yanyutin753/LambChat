import { useState, useEffect } from "react";
import {
  AlertCircle,
  X,
  Send,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ListOrdered,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { PendingApproval, FormField } from "../../types";
import { Checkbox } from "../common/Checkbox";

interface ApprovalPanelProps {
  approvals: PendingApproval[];
  onRespond: (
    id: string,
    response: Record<string, unknown>,
    approved: boolean,
  ) => void;
  isLoading: boolean;
}

// Form field renderer component
function FormFieldRenderer({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled: boolean;
}) {
  const baseInputClasses =
    "glass-input w-full rounded-xl pl-4 pr-10 py-2.5 text-sm text-stone-900 placeholder-stone-400 transition-all duration-200 focus:outline-none disabled:opacity-50 dark:text-stone-100 dark:placeholder-stone-500";

  switch (field.type) {
    case "text":
      return (
        <input
          type="text"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
          className={baseInputClasses}
        />
      );

    case "textarea":
      return (
        <textarea
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
          rows={3}
          className={`${baseInputClasses} resize-none`}
        />
      );

    case "number":
      return (
        <input
          type="number"
          value={(value as number) ?? ""}
          onChange={(e) =>
            onChange(e.target.value ? Number(e.target.value) : "")
          }
          placeholder={field.placeholder}
          disabled={disabled}
          className={baseInputClasses}
        />
      );

    case "checkbox":
      return (
        <label className="flex items-center gap-3 cursor-pointer">
          <Checkbox
            checked={(value as boolean) ?? false}
            onChange={() => onChange(!((value as boolean) ?? false))}
            disabled={disabled}
          />
          <span className="text-sm text-stone-700 dark:text-stone-300">
            {field.label}
          </span>
        </label>
      );

    case "select":
      return (
        <div className="relative">
          <select
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className={`${baseInputClasses} appearance-none`}
          >
            <option value="" disabled>
              {field.placeholder || "Select an option"}
            </option>
            {field.options?.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <ChevronDown
            size={16}
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-stone-400"
          />
        </div>
      );

    case "multi_select": {
      const selectedValues = (value as string[]) ?? [];
      return (
        <div className="flex flex-wrap gap-2">
          {field.options?.map((option) => {
            const isSelected = selectedValues.includes(option);
            return (
              <button
                key={option}
                type="button"
                onClick={() => {
                  if (isSelected) {
                    onChange(selectedValues.filter((v) => v !== option));
                  } else {
                    onChange([...selectedValues, option]);
                  }
                }}
                disabled={disabled}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isSelected
                    ? "bg-black text-white dark:bg-white dark:text-black"
                    : "border border-stone-200 bg-[var(--theme-bg-card)] text-stone-700 hover:bg-[var(--glass-bg-subtle)] dark:text-stone-300"
                } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {option}
              </button>
            );
          })}
        </div>
      );
    }

    default:
      return null;
  }
}

export function ApprovalPanel({
  approvals,
  onRespond,
  isLoading,
}: ApprovalPanelProps) {
  const { t } = useTranslation();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [formValues, setFormValues] = useState<
    Record<string, Record<string, unknown>>
  >({});

  // Initialize form values from field defaults when approvals change
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
      // Remove values for approvals that no longer exist
      Object.keys(newValues).forEach((id) => {
        if (!approvals.find((a) => a.id === id)) {
          delete newValues[id];
        }
      });
      return newValues;
    });
  }, [approvals]);

  // Get default value based on field type
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
        return "";
      case "multi_select":
        return [];
      default:
        return null;
    }
  }

  // Adjust currentIndex when approvals count changes
  useEffect(() => {
    if (currentIndex >= approvals.length) {
      setCurrentIndex(Math.max(0, approvals.length - 1));
    }
  }, [approvals.length, currentIndex]);

  if (approvals.length === 0) return null;

  // Boundary protection
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
    onRespond(currentApproval.id, currentFormValues, true);
  };

  const handleCancel = () => {
    onRespond(currentApproval.id, {}, false);
  };

  const isSubmitDisabled =
    isLoading || !isFormValid(currentApproval.fields, currentFormValues);

  function isFormValid(
    fields: FormField[],
    values: Record<string, unknown>,
  ): boolean {
    return fields.every((field) => {
      if (!field.required) return true;
      const value = values[field.name];
      if (value === undefined || value === null) return false;
      if (typeof value === "string" && value.trim() === "") return false;
      if (Array.isArray(value) && value.length === 0) return false;
      return true;
    });
  }

  return (
    <div className="w-full max-h-[60dvh] shrink min-h-0 overflow-y-auto overscroll-contain px-3 py-2 sm:px-4 sm:py-3 bg-white dark:bg-stone-900">
      <div className="mx-auto max-w-3xl xl:max-w-5xl">
        {/* Navigation control bar */}
        {approvals.length > 1 && (
          <div className="mb-2 flex items-center justify-between px-1">
            <div className="flex items-center gap-1.5 text-xs text-stone-500 dark:text-stone-400">
              <ListOrdered size={14} />
              <span>
                {currentIndex + 1} / {approvals.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={goToPrev}
                disabled={currentIndex === 0}
                className="p-1.5 rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] text-stone-600 hover:bg-[var(--glass-bg-subtle)] disabled:opacity-40 disabled:cursor-not-allowed dark:text-stone-300"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={goToNext}
                disabled={currentIndex === approvals.length - 1}
                className="p-1.5 rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] text-stone-600 hover:bg-[var(--glass-bg-subtle)] disabled:opacity-40 disabled:cursor-not-allowed dark:text-stone-300"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        <div className="glass-card rounded-2xl" key={currentApproval.id}>
          {/* Header */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--glass-border)]">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
              <AlertCircle
                size={12}
                className="text-amber-600 dark:text-amber-400"
              />
            </div>
            <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
              {t("approvals.needsConfirmation")}
            </span>
          </div>

          {/* Message content */}
          <div className="px-4 py-3 sm:px-5">
            <div className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed text-stone-800 dark:text-stone-200 prose-p:my-1 prose-headings:my-2 prose-headings:font-semibold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-code:rounded-md prose-code:bg-stone-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-stone-600 dark:prose-code:bg-stone-700 dark:prose-code:text-stone-400">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                {currentApproval.message}
              </ReactMarkdown>
            </div>
          </div>

          {/* Form fields */}
          {currentApproval.fields.length > 0 && (
            <div className="px-4 py-3 sm:px-5 space-y-4 border-t border-[var(--glass-border)]">
              {currentApproval.fields.map((field) => (
                <div key={field.name} className="space-y-1.5">
                  {field.type !== "checkbox" && (
                    <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                      {field.label}
                      {field.required && (
                        <span className="text-red-500 ml-1">*</span>
                      )}
                    </label>
                  )}
                  <FormFieldRenderer
                    field={field}
                    value={currentFormValues[field.name]}
                    onChange={(value) => handleFieldChange(field.name, value)}
                    disabled={isLoading}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="px-4 py-3 sm:px-5 bg-[var(--glass-bg-subtle)]">
            <div className="flex flex-col gap-2 sm:flex-row sm:gap-3">
              <button
                onClick={handleSubmit}
                disabled={isSubmitDisabled}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-black px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-stone-800 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:bg-white dark:text-black dark:hover:bg-stone-100"
              >
                <Send size={18} />
                <span>{t("approvals.submit")}</span>
              </button>
              <button
                onClick={handleCancel}
                disabled={isLoading}
                className="btn-secondary px-4 py-2.5 flex flex-1 items-center justify-center gap-2 rounded-xl text-sm font-medium transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <X size={18} />
                <span>{t("approvals.cancel")}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
