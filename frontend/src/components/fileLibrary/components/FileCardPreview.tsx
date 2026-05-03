import { clsx } from "clsx";
import {
  Code2,
  FileText,
  FolderKanban,
  Image as ImageIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getFullUrl } from "../../../services/api";
import type { FileCardPreview as FileCardPreviewModel } from "../utils";

interface FileCardPreviewProps {
  preview: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}

const toneStyles = {
  blue: {
    shell: "bg-sky-50 text-sky-950 dark:bg-sky-950/30 dark:text-sky-50",
    badge:
      "bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-400/10 dark:text-sky-200 dark:ring-sky-300/20",
    line: "bg-white/72 dark:bg-white/[0.06]",
    accent: "bg-sky-400",
  },
  green: {
    shell:
      "bg-emerald-50 text-emerald-950 dark:bg-emerald-950/30 dark:text-emerald-50",
    badge:
      "bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-200 dark:ring-emerald-300/20",
    line: "bg-white/72 dark:bg-white/[0.06]",
    accent: "bg-emerald-400",
  },
  amber: {
    shell: "bg-amber-50 text-amber-950 dark:bg-amber-950/30 dark:text-amber-50",
    badge:
      "bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-300/20",
    line: "bg-white/72 dark:bg-white/[0.06]",
    accent: "bg-amber-400",
  },
  rose: {
    shell: "bg-rose-50 text-rose-950 dark:bg-rose-950/30 dark:text-rose-50",
    badge:
      "bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-400/10 dark:text-rose-200 dark:ring-rose-300/20",
    line: "bg-white/72 dark:bg-white/[0.06]",
    accent: "bg-rose-400",
  },
  violet: {
    shell:
      "bg-violet-50 text-violet-950 dark:bg-violet-950/30 dark:text-violet-50",
    badge:
      "bg-violet-100 text-violet-700 ring-violet-200 dark:bg-violet-400/10 dark:text-violet-200 dark:ring-violet-300/20",
    line: "bg-white/72 dark:bg-white/[0.06]",
    accent: "bg-violet-400",
  },
  stone: {
    shell:
      "bg-stone-50 text-stone-900 dark:bg-stone-900/70 dark:text-stone-100",
    badge:
      "bg-stone-100 text-stone-600 ring-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:ring-stone-700",
    line: "bg-white/78 dark:bg-white/[0.06]",
    accent: "bg-stone-400",
  },
} as const;

const kindIcon: Partial<Record<FileCardPreviewModel["kind"], LucideIcon>> = {
  code: Code2,
  image: ImageIcon,
  markdown: FileText,
  project: FolderKanban,
  text: FileText,
  document: FileText,
};

function lineWidth(index: number): string {
  if (index === 0) return "w-[86%]";
  if (index === 1) return "w-[72%]";
  if (index === 2) return "w-[92%]";
  return "w-[64%]";
}

export function FileCardPreview({
  preview,
  icon,
  compact = false,
}: FileCardPreviewProps) {
  const imageUrl = preview.imageUrl ? getFullUrl(preview.imageUrl) : "";
  const styles = toneStyles[preview.tone];
  const PreviewIcon = kindIcon[preview.kind] || icon;

  if (preview.kind === "image" && imageUrl) {
    return (
      <img
        src={imageUrl}
        alt={preview.title}
        className="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.02]"
        loading="lazy"
      />
    );
  }

  return (
    <div
      className={clsx(
        "relative flex h-full w-full flex-col overflow-hidden",
        styles.shell,
        compact ? "p-1.5" : "p-3.5",
      )}
    >
      <div className={clsx("absolute inset-x-0 top-0 h-1", styles.accent)} />
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span
          className={clsx(
            "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold leading-4 ring-1",
            styles.badge,
          )}
        >
          {preview.badge}
        </span>
        <PreviewIcon
          size={compact ? 13 : 16}
          strokeWidth={1.7}
          className="shrink-0 opacity-70"
        />
      </div>

      {!compact && (
        <div className="min-w-0 pt-2.5">
          <p className="truncate text-[15px] font-semibold leading-5">
            {preview.title}
          </p>
          <p className="mt-1 truncate text-[11px] leading-4 opacity-65">
            {preview.subtitle}
          </p>
        </div>
      )}

      <div
        className={clsx("mt-auto flex flex-col", compact ? "gap-1" : "gap-1.5")}
      >
        {preview.lines.length > 0 ? (
          preview.lines.slice(0, compact ? 2 : 4).map((line, index) => (
            <div
              key={`${line}-${index}`}
              className={clsx(
                "min-w-0 truncate rounded px-1.5 font-mono text-[10px] leading-5 opacity-80",
                styles.line,
                compact ? "h-4 leading-4" : lineWidth(index),
              )}
            >
              {line}
            </div>
          ))
        ) : (
          <div
            className={clsx(
              "rounded px-1.5 text-[10px] leading-5 opacity-75",
              styles.line,
            )}
          >
            {preview.subtitle}
          </div>
        )}
      </div>
    </div>
  );
}
