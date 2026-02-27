import { useState } from "react";
import { AlertCircle, Check, X, Send, CornerDownLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { PendingApproval } from "../../types";

interface ApprovalPanelProps {
  approvals: PendingApproval[];
  onRespond: (id: string, response: string, approved: boolean) => void;
  isLoading: boolean;
}

export function ApprovalPanel({
  approvals,
  onRespond,
  isLoading,
}: ApprovalPanelProps) {
  const { t } = useTranslation();
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [focusedInput, setFocusedInput] = useState<string | null>(null);

  if (approvals.length === 0) return null;

  return (
    <div className="w-full px-3 py-2 sm:px-4 sm:py-3 bg-white dark:bg-stone-900">
      <div className="mx-auto max-w-3xl xl:max-w-5xl space-y-2">
        {approvals.map((approval, index) => (
          <div
            key={approval.id}
            className="overflow-hidden rounded-2xl border border-gray-200 bg-gray-50 shadow-sm transition-all duration-200 dark:border-stone-700 dark:bg-stone-800"
            style={{
              animation: `slide-in-from-bottom-2 0.3s ease-out ${
                index * 0.05
              }s both`,
            }}
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
                  {approval.message}
                </ReactMarkdown>
              </div>
            </div>

            {/* Actions */}
            <div className="px-4 py-3 sm:px-5 bg-gray-100/50 dark:bg-stone-800/50">
              {/* Confirm type */}
              {approval.type === "confirm" && (
                <div className="flex flex-col gap-2 sm:flex-row sm:gap-3">
                  <button
                    onClick={() => onRespond(approval.id, "yes", true)}
                    disabled={isLoading}
                    className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-black px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-gray-800 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:bg-white dark:text-black dark:hover:bg-gray-100"
                  >
                    <Check size={18} />
                    <span>{t("approvals.approve")}</span>
                  </button>
                  <button
                    onClick={() => onRespond(approval.id, "no", false)}
                    disabled={isLoading}
                    className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-all hover:bg-gray-50 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-transparent dark:text-stone-200 dark:hover:bg-stone-700"
                  >
                    <X size={18} />
                    <span>{t("approvals.reject")}</span>
                  </button>
                </div>
              )}

              {/* Text input type */}
              {approval.type === "text" && (
                <div className="flex flex-col gap-2 sm:flex-row sm:gap-3">
                  <div
                    className={`relative flex-1 flex items-center rounded-xl border bg-white transition-all duration-200 dark:bg-stone-700 ${
                      focusedInput === approval.id
                        ? "border-gray-400 shadow-sm dark:border-stone-500"
                        : "border-gray-200 dark:border-stone-600"
                    }`}
                  >
                    <input
                      type="text"
                      value={responses[approval.id] || ""}
                      onChange={(e) =>
                        setResponses((prev) => ({
                          ...prev,
                          [approval.id]: e.target.value,
                        }))
                      }
                      onFocus={() => setFocusedInput(approval.id)}
                      onBlur={() => setFocusedInput(null)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          onRespond(
                            approval.id,
                            responses[approval.id] || approval.default || "",
                            true,
                          );
                        }
                      }}
                      placeholder={
                        approval.default || t("approvals.enterResponse")
                      }
                      disabled={isLoading}
                      className="w-full bg-transparent px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none disabled:opacity-50 dark:text-stone-100 dark:placeholder-stone-500"
                    />
                    <kbd className="mr-3 hidden rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-400 dark:bg-stone-600 dark:text-stone-400 sm:inline-flex items-center gap-1">
                      <CornerDownLeft size={8} />
                    </kbd>
                  </div>
                  <button
                    onClick={() =>
                      onRespond(
                        approval.id,
                        responses[approval.id] || approval.default || "",
                        true,
                      )
                    }
                    disabled={isLoading || !responses[approval.id]}
                    className={`flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium shadow-sm transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed ${
                      responses[approval.id]
                        ? "bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-100"
                        : "bg-gray-200 text-gray-400 dark:bg-stone-700 dark:text-stone-500"
                    }`}
                  >
                    <Send size={18} />
                    <span className="sm:hidden">{t("approvals.send")}</span>
                  </button>
                </div>
              )}

              {/* Choice type */}
              {approval.type === "choice" && approval.choices.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {approval.choices.map((choice: string) => (
                    <button
                      key={choice}
                      onClick={() => onRespond(approval.id, choice, true)}
                      disabled={isLoading}
                      className="rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-all hover:border-gray-300 hover:bg-gray-50 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-stone-700 dark:text-stone-200 dark:hover:border-stone-500 dark:hover:bg-stone-600"
                    >
                      {choice}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
