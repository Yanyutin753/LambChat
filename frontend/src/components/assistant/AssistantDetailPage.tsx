import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  type LucideIcon,
  Check,
  ChevronRight,
  Clipboard,
  Globe,
  Lightbulb,
  Lock,
  Package,
  Sparkles,
} from "lucide-react";

import type { Assistant } from "../../types";
import { useAssistants } from "../../hooks/useAssistants";
import { getCategoryById } from "./categories";
import { nameToGradient } from "./gradientUtils";

interface AssistantDetailPageProps {
  assistantId: string;
  onBack: () => void;
  onStartChat: (assistant: Assistant) => void;
  onViewAssistant: (assistantId: string) => void;
}

function CategoryBadge({ categoryId }: { categoryId?: string }) {
  const category = getCategoryById(categoryId ?? "");
  if (!category) return null;
  const Icon: LucideIcon = category.icon;
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800/50 dark:text-stone-400">
      <Icon size={11} />
      {category.label}
    </span>
  );
}

function RelatedAssistantRow({
  assistant,
  onClick,
}: {
  assistant: Assistant;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-stone-100 dark:hover:bg-stone-800/60"
    >
      <div
        className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg ring-1 ring-white/60"
        style={{ background: nameToGradient(assistant.name) }}
      >
        {assistant.avatar_url ? (
          <img
            src={assistant.avatar_url}
            alt={assistant.name}
            className="size-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <Sparkles size={14} className="text-white/90" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-stone-800 dark:text-stone-200">
          {assistant.name}
        </p>
        <p className="truncate text-[11px] text-stone-400 dark:text-stone-500">
          {assistant.description || "No description"}
        </p>
      </div>
      <ChevronRight
        size={16}
        className="shrink-0 text-stone-300 dark:text-stone-600"
      />
    </button>
  );
}

export function AssistantDetailPage({
  assistantId,
  onBack,
  onStartChat,
  onViewAssistant,
}: AssistantDetailPageProps) {
  const { assistants, isLoading } = useAssistants({ scope: "all" });
  const [copied, setCopied] = useState(false);

  const assistant = useMemo(
    () => assistants.find((a) => a.assistant_id === assistantId) ?? null,
    [assistants, assistantId],
  );

  const relatedAssistants = useMemo(() => {
    if (!assistant) return [];
    return assistants
      .filter(
        (a) =>
          a.assistant_id !== assistant.assistant_id &&
          a.category === assistant.category,
      )
      .slice(0, 6);
  }, [assistants, assistant]);

  const handleCopy = useCallback(async () => {
    if (!assistant) return;
    try {
      await navigator.clipboard.writeText(assistant.system_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may not be available in all contexts
    }
  }, [assistant]);

  // Reset copied state when assistant changes
  useEffect(() => {
    setCopied(false);
  }, [assistantId]);

  // Loading state
  if (isLoading && !assistant) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-3 border-b border-stone-200/80 bg-white/80 px-6 py-4 backdrop-blur-sm dark:border-stone-800/50 dark:bg-stone-950/80">
          <div className="size-8 animate-pulse rounded-lg bg-stone-200 dark:bg-stone-700" />
          <div className="h-5 w-32 animate-pulse rounded bg-stone-200 dark:bg-stone-700" />
        </div>
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="text-[14px] text-stone-400 dark:text-stone-500">
            Loading assistant...
          </div>
        </div>
      </div>
    );
  }

  // Not-found state
  if (!assistant) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-3 border-b border-stone-200/80 bg-white/80 px-6 py-4 backdrop-blur-sm dark:border-stone-800/50 dark:bg-stone-950/80">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-stone-100"
          >
            <ArrowLeft size={16} />
            Back
          </button>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
          <Package size={32} className="text-stone-300 dark:text-stone-600" />
          <div className="text-center">
            <p className="text-[15px] font-medium text-stone-700 dark:text-stone-300">
              Assistant not found
            </p>
            <p className="mt-1 text-[13px] text-stone-400 dark:text-stone-500">
              The assistant you are looking for does not exist or has been
              removed.
            </p>
          </div>
          <button
            type="button"
            onClick={onBack}
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
          >
            <ArrowLeft size={14} />
            Go Back
          </button>
        </div>
      </div>
    );
  }

  const ScopeIcon = assistant.scope === "public" ? Globe : Lock;

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200/80 bg-white/80 px-6 py-4 backdrop-blur-sm dark:border-stone-800/50 dark:bg-stone-950/80">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-stone-100"
        >
          <ArrowLeft size={16} />
          Back
        </button>
        <button
          type="button"
          onClick={() => onStartChat(assistant)}
          className="hidden items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200 lg:inline-flex"
        >
          <Sparkles size={14} />
          Start Chat
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* Info card */}
        <div className="rounded-xl border border-stone-200/70 bg-white p-6 shadow-sm dark:border-stone-800/50 dark:bg-stone-900/60">
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
            {/* Avatar */}
            <div
              className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-xl ring-2 ring-white/60 shadow-sm"
              style={{ background: nameToGradient(assistant.name) }}
            >
              {assistant.avatar_url ? (
                <img
                  src={assistant.avatar_url}
                  alt={assistant.name}
                  className="size-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <Sparkles size={24} className="text-white/90" />
              )}
            </div>

            {/* Name, scope, category, description */}
            <div className="flex-1 text-center sm:text-left">
              <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-50">
                  {assistant.name}
                </h1>
                <ScopeIcon
                  size={16}
                  className={
                    assistant.scope === "public"
                      ? "text-sky-500 dark:text-sky-400"
                      : "text-stone-400 dark:text-stone-500"
                  }
                />
              </div>
              {assistant.category && (
                <div className="mt-2">
                  <CategoryBadge categoryId={assistant.category} />
                </div>
              )}
              {assistant.description && (
                <p className="mt-3 text-[13.5px] leading-relaxed text-stone-500 dark:text-stone-400">
                  {assistant.description}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Two-column layout: prompt + related */}
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          {/* System prompt — left 2/3 */}
          <div className="lg:col-span-2">
            <div className="rounded-xl border border-stone-200/70 bg-white shadow-sm dark:border-stone-800/50 dark:bg-stone-900/60">
              {/* Prompt header */}
              <div className="flex items-center justify-between border-b border-stone-100 px-5 py-3.5 dark:border-stone-800/40">
                <div className="flex items-center gap-2 text-[13px] font-semibold text-stone-700 dark:text-stone-200">
                  <Clipboard
                    size={15}
                    className="text-stone-400 dark:text-stone-500"
                  />
                  System Prompt
                </div>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
                >
                  {copied ? (
                    <>
                      <Check size={12} className="text-green-500" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Clipboard size={12} />
                      Copy
                    </>
                  )}
                </button>
              </div>

              {/* Prompt content */}
              <pre className="max-h-[400px] overflow-y-auto px-5 py-4 font-mono text-[12.5px] leading-6 text-stone-700 dark:text-stone-300">
                {assistant.system_prompt}
              </pre>
            </div>

            {/* Blue tip bar */}
            <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-blue-100 bg-blue-50/80 px-4 py-3 dark:border-blue-900/30 dark:bg-blue-950/20">
              <Lightbulb
                size={15}
                className="mt-0.5 shrink-0 text-blue-500 dark:text-blue-400"
              />
              <p className="text-[12.5px] leading-relaxed text-blue-700 dark:text-blue-300">
                Starting a chat with this assistant will inject its system
                prompt into the conversation. The assistant&apos;s persona and
                instructions will guide the AI&apos;s responses throughout your
                session.
              </p>
            </div>
          </div>

          {/* Related assistants — right 1/3 */}
          <div className="lg:col-span-1">
            <div className="rounded-xl border border-stone-200/70 bg-white shadow-sm dark:border-stone-800/50 dark:bg-stone-900/60">
              <div className="border-b border-stone-100 px-5 py-3.5 dark:border-stone-800/40">
                <h3 className="text-[13px] font-semibold text-stone-700 dark:text-stone-200">
                  Similar Assistants
                </h3>
              </div>

              {relatedAssistants.length > 0 ? (
                <div className="divide-y divide-stone-100 dark:divide-stone-800/40">
                  {relatedAssistants.map((related) => (
                    <div key={related.assistant_id} className="px-2 py-1">
                      <RelatedAssistantRow
                        assistant={related}
                        onClick={() => onViewAssistant(related.assistant_id)}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 px-5 py-10">
                  <Package
                    size={24}
                    className="text-stone-300 dark:text-stone-600"
                  />
                  <p className="text-[12.5px] text-stone-400 dark:text-stone-500">
                    No similar assistants found
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Mobile "Start Chat" button — hidden on lg */}
      <div className="border-t border-stone-200/80 bg-white/80 px-6 py-4 backdrop-blur-sm dark:border-stone-800/50 dark:bg-stone-950/80 lg:hidden">
        <button
          type="button"
          onClick={() => onStartChat(assistant)}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-stone-900 py-3 text-[14px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
        >
          <Sparkles size={16} />
          Start Chatting with This Assistant
        </button>
      </div>
    </div>
  );
}
