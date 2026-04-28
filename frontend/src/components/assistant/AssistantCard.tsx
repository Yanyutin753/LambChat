import {
  type LucideIcon,
  CopyPlus,
  Eye,
  Globe,
  Lock,
  Pencil,
  Sparkles,
  Trash2,
} from "lucide-react";

import type { Assistant } from "../../types";
import { getCategoryById } from "./categories";
import { nameToGradient } from "./gradientUtils";

interface AssistantCardProps {
  assistant: Assistant;
  isAdmin: boolean;
  onClone: (assistant: Assistant) => void;
  onEdit: (assistant: Assistant) => void;
  onDelete: (assistant: Assistant) => void;
  onView: (assistant: Assistant) => void;
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

export function AssistantCard({
  assistant,
  isAdmin,
  onClone,
  onEdit,
  onDelete,
  onView,
}: AssistantCardProps) {
  const canEdit =
    assistant.scope === "private" || (assistant.scope === "public" && isAdmin);

  const ScopeIcon = assistant.scope === "public" ? Globe : Lock;

  return (
    <article className="group flex h-full flex-col overflow-hidden rounded-xl border border-stone-200/70 bg-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-stone-800/50 dark:bg-stone-900/60">
      {/* Gradient header bar */}
      <div
        className="h-12 w-full shrink-0"
        style={{ background: nameToGradient(assistant.name) }}
      />

      {/* Clickable body */}
      <button
        type="button"
        onClick={() => onView(assistant)}
        className="flex min-w-0 flex-1 cursor-pointer flex-col text-left"
      >
        {/* Avatar + name + scope */}
        <div className="flex items-start gap-3 px-4 pt-4 pb-2">
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
              <Sparkles size={16} className="text-white/90" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h3 className="truncate text-[14px] font-semibold text-stone-900 dark:text-stone-50">
                {assistant.name}
              </h3>
              <ScopeIcon
                size={13}
                className={`shrink-0 ${
                  assistant.scope === "public"
                    ? "text-sky-500 dark:text-sky-400"
                    : "text-stone-400 dark:text-stone-500"
                }`}
              />
            </div>
            {assistant.category && (
              <div className="mt-1">
                <CategoryBadge categoryId={assistant.category} />
              </div>
            )}
          </div>
        </div>

        {/* Description */}
        <p className="px-4 line-clamp-2 text-[12.5px] leading-relaxed text-stone-500 dark:text-stone-400">
          {assistant.description || "No description yet."}
        </p>

        {/* Tags */}
        {assistant.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 px-4 pt-2.5">
            {assistant.tags.map((tag) => (
              <span
                key={tag}
                className="rounded bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500 dark:bg-stone-800/50 dark:text-stone-400"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* System prompt preview */}
        <div className="mx-4 mt-3 flex-1 rounded-lg bg-stone-50 px-3 py-2.5 dark:bg-stone-800/40">
          <p className="line-clamp-3 whitespace-pre-wrap font-mono text-[11px] leading-5 text-stone-400 dark:text-stone-500">
            {assistant.system_prompt}
          </p>
        </div>
      </button>

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 border-t border-stone-100 px-4 py-3 dark:border-stone-800/40">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onView(assistant);
          }}
          className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
        >
          <Eye size={12} />
          View
        </button>

        {assistant.scope === "public" && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClone(assistant);
            }}
            className="inline-flex items-center gap-1 rounded-md bg-stone-900 px-2.5 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
          >
            <CopyPlus size={12} />
            Clone
          </button>
        )}

        {canEdit && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onEdit(assistant);
            }}
            className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
          >
            <Pencil size={12} />
            Edit
          </button>
        )}

        {assistant.scope === "private" && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(assistant);
            }}
            className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-rose-500 transition-colors hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/30"
          >
            <Trash2 size={12} />
            Delete
          </button>
        )}
      </div>
    </article>
  );
}
