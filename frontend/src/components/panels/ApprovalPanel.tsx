import { useState, useEffect } from "react";
import {
  AlertCircle,
  Check,
  X,
  Send,
  ChevronLeft,
  ChevronRight,
  ListOrdered,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { PendingApproval, FormField } from "../../types";

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
    "w-full rounded-xl border bg-white px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 transition-all duration-200 focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 disabled:opacity-50 dark:bg-stone-700 dark:text-stone-100 dark:placeholder-stone-500 dark:border-stone-600 dark:focus:border-stone-500 dark:focus:ring-stone-500/20";

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
          <div className="relative">
            <input
              type="checkbox"
              checked={(value as boolean) ?? false}
              onChange={(e) => onChange(e.target.checked)}
              disabled={disabled}
              className="sr-only"
            />
            <div
              className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
                (value as boolean) ?? false
                  ? "bg-black border-black dark:bg-white dark:border-white"
                  : "border-gray-300 bg-white dark:border-stone-600 dark:bg-stone-700"
              } ${disabled ? "opacity-50" : ""}`}
            >
              {(value as boolean) ?? false ? (
                <Check size={14} className="text-white dark:text-black" />
              ) : null}
            </div>
          </div>
          <span className="text-sm text-gray-700 dark:text-stone-300">
            {field.label}
          </span>
        </label>
      );

    case "select":
      return (
        <select
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={baseInputClasses}
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
                    : "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
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
    <div className="w-full px-3 py-2 sm:px-4 sm:py-3 bg-white dark:bg-stone-900">
      <div className="mx-auto max-w-3xl xl:max-w-5xl">
        {/* Navigation control bar */}
        {approvals.length > 1 && (
          <div className="mb-2 flex items-center justify-between px-1">
            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-stone-400">
              <ListOrdered size={14} />
              <span>
                {currentIndex + 1} / {approvals.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={goToPrev}
                disabled={currentIndex === 0}
                className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={goToNext}
                disabled={currentIndex === approvals.length - 1}
                className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        <div
          className="overflow-hidden rounded-2xl border border-gray-200 bg-gray-50 shadow-sm transition-all duration-200 dark:border-stone-700 dark:bg-stone-800"
          key={currentApproval.id}
        >
          {/* Header */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-100 dark:border-stone-700">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
              <AlertCircle
                size={12}
                className="text-blue-600 dark:text-blue-400"
              />
            </div>
            <span className="text-xs font-medium text-gray-500 dark:text-stone-400">
              {t("approvals.needsConfirmation")}
            </span>
          </div>

          {/* Message content */}
          <div className="px-4 py-3 sm:px-5">
            <div className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed text-gray-800 dark:text-stone-200 prose-p:my-1 prose-headings:my-2 prose-headings:font-semibold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-code:rounded-md prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-blue-600 dark:prose-code:bg-stone-700 dark:prose-code:text-blue-400">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                {currentApproval.message}
              </ReactMarkdown>
            </div>
          </div>

          {/* Form fields */}
          {currentApproval.fields.length > 0 && (
            <div className="px-4 py-3 sm:px-5 space-y-4 border-t border-gray-100 dark:border-stone-700">
              {currentApproval.fields.map((field) => (
                <div key={field.name} className="space-y-1.5">
                  {field.type !== "checkbox" && (
                    <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
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
          <div className="px-4 py-3 sm:px-5 bg-gray-100/50 dark:bg-stone-800/50">
            <div className="flex flex-col gap-2 sm:flex-row sm:gap-3">
              <button
                onClick={handleSubmit}
                disabled={isSubmitDisabled}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-black px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-gray-800 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:bg-white dark:text-black dark:hover:bg-gray-100"
              >
                <Send size={18} />
                <span>{t("approvals.submit")}</span>
              </button>
              <button
                onClick={handleCancel}
                disabled={isLoading}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-all hover:bg-gray-50 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-transparent dark:text-stone-200 dark:hover:bg-stone-700"
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
