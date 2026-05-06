import { clsx } from "clsx";
import { Braces, Layers } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getFullUrl } from "../../../services/api";
import type { FileCardPreview as FileCardPreviewModel } from "../utils";

interface FileCardPreviewProps {
  preview: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}

/* ── Per-file-type icon tint ── */

const ICON_TINT: Record<string, string> = {
  amber: "text-amber-500 dark:text-amber-400",
  blue: "text-blue-500 dark:text-blue-400",
  cyan: "text-cyan-500 dark:text-cyan-400",
  emerald: "text-emerald-500 dark:text-emerald-400",
  green: "text-green-500 dark:text-green-400",
  indigo: "text-indigo-500 dark:text-indigo-400",
  lime: "text-lime-500 dark:text-lime-400",
  orange: "text-orange-500 dark:text-orange-400",
  pink: "text-pink-500 dark:text-pink-400",
  purple: "text-purple-500 dark:text-purple-400",
  red: "text-red-500 dark:text-red-400",
  rose: "text-rose-500 dark:text-rose-400",
  sky: "text-sky-500 dark:text-sky-400",
  slate: "text-slate-500 dark:text-slate-400",
  stone: "text-stone-500 dark:text-stone-400",
  teal: "text-teal-500 dark:text-teal-400",
  violet: "text-violet-500 dark:text-violet-400",
  yellow: "text-yellow-500 dark:text-yellow-400",
  zinc: "text-zinc-500 dark:text-zinc-400",
};

const BADGE_TINT: Record<string, string> = {
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  blue: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  cyan: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300",
  emerald:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  green: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  indigo:
    "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  lime: "bg-lime-100 text-lime-700 dark:bg-lime-900/30 dark:text-lime-300",
  orange:
    "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  pink: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  purple:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  red: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  rose: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  sky: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  slate: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  stone: "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300",
  teal: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
  violet:
    "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  yellow:
    "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300",
  zinc: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
};

/* ── Cover layout ──────────────────────────────────────── */

function CoverLayout({
  colorName,
  icon: Icon,
  badge,
  subtitle,
  compact,
  topRight,
}: {
  colorName: string;
  icon: LucideIcon;
  badge: string;
  title?: string;
  subtitle?: string;
  compact?: boolean;
  topRight?: React.ReactNode;
}) {
  const tint = ICON_TINT[colorName] ?? ICON_TINT.stone;
  const badgeCls = BADGE_TINT[colorName] ?? BADGE_TINT.stone;

  if (compact) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-stone-50 dark:bg-stone-800/40">
        <Icon size={17} strokeWidth={2} className={tint} />
      </div>
    );
  }

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-stone-50 dark:bg-stone-800/30">
      {/* Centered icon */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <Icon
          size={42}
          strokeWidth={1.1}
          className={clsx("relative opacity-[0.15]", tint)}
        />
      </div>

      {/* Header */}
      <div className="relative z-10 flex items-center justify-between px-3 pt-2.5">
        <span
          className={clsx(
            "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold tracking-wide",
            badgeCls,
          )}
        >
          {badge}
        </span>
        {topRight}
      </div>

      {/* Footer */}
      <div className="relative z-10 mt-auto px-3 pb-3">
        {subtitle && (
          <p className="truncate text-[10px] leading-3 text-stone-400 dark:text-stone-500">
            {subtitle}
          </p>
        )}
      </div>
    </div>
  );
}

/* ── Cover variants ────────────────────────────────────── */

function MarkdownCover({
  p,
  icon,
  compact,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}) {
  const tint = ICON_TINT[p.colorName] ?? ICON_TINT.stone;
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge="Markdown"
      subtitle={p.subtitle}
      compact={compact}
      topRight={
        p.language && (
          <span className={clsx("text-[10px]", tint)}>{p.language}</span>
        )
      }
    />
  );
}

function CodeCover({
  p,
  icon,
  compact,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}) {
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge={p.badge}
      subtitle={p.subtitle}
      compact={compact}
      topRight={
        <div className="flex gap-1">
          <span className="h-[6px] w-[6px] rounded-full bg-stone-300 dark:bg-stone-600" />
          <span className="h-[6px] w-[6px] rounded-full bg-stone-200 dark:bg-stone-700" />
          <span className="h-[6px] w-[6px] rounded-full bg-stone-100 dark:bg-stone-800" />
        </div>
      }
    />
  );
}

function ProjectCover({
  p,
  icon,
  compact,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}) {
  const tint = ICON_TINT[p.colorName] ?? ICON_TINT.stone;
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge={p.badge}
      compact={compact}
      topRight={
        <span className={clsx("flex items-center gap-1 text-[10px]", tint)}>
          <Layers size={10} />
          {p.subtitle}
        </span>
      }
    />
  );
}

function DataCover({
  p,
  icon,
  compact,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}) {
  const tint = ICON_TINT[p.colorName] ?? ICON_TINT.stone;
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge={p.badge}
      compact={compact}
      topRight={<Braces size={12} className={clsx("opacity-40", tint)} />}
    />
  );
}

function DocumentCover({
  p,
  icon,
  compact,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}) {
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge={p.badge}
      subtitle={p.subtitle}
      compact={compact}
    />
  );
}

/* ── Main ──────────────────────────────────────────────── */

export function FileCardPreview({
  preview,
  icon,
  compact = false,
}: FileCardPreviewProps) {
  const imageUrl = preview.imageUrl ? getFullUrl(preview.imageUrl) : "";

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

  switch (preview.kind) {
    case "markdown":
      return <MarkdownCover p={preview} icon={icon} compact={compact} />;
    case "code":
      return <CodeCover p={preview} icon={icon} compact={compact} />;
    case "project":
      return <ProjectCover p={preview} icon={icon} compact={compact} />;
    case "text":
      return <DataCover p={preview} icon={icon} compact={compact} />;
    default:
      return <DocumentCover p={preview} icon={icon} compact={compact} />;
  }
}
