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

/* ── Accent colors (per file type, for bar only) ── */

function makeAccent(name: string) {
  const neu = new Set(["stone", "slate", "zinc", "neutral", "gray"]).has(name);
  return {
    shell: neu
      ? `bg-gradient-to-b from-${name}-50 to-${name}-100/60 text-${name}-900 dark:from-${name}-900/50 dark:to-${name}-950/60 dark:text-${name}-100`
      : `bg-gradient-to-b from-${name}-50 to-${name}-100/60 text-${name}-950 dark:from-${name}-950/30 dark:to-${name}-950/60 dark:text-${name}-50`,
    bar: `bg-${name}-400`,
    muted: `text-${name}-500 dark:text-${name}-400`,
    badge: neu
      ? `bg-${name}-100 text-${name}-600 ring-${name}-200 dark:bg-${name}-800 dark:text-${name}-300 dark:ring-${name}-700`
      : `bg-${name}-100 text-${name}-700 ring-${name}-200 dark:bg-${name}-400/10 dark:text-${name}-200 dark:ring-${name}-300/20`,
  };
}

const ACCENTS: Record<string, ReturnType<typeof makeAccent>> = {
  amber: makeAccent("amber"),
  blue: makeAccent("blue"),
  cyan: makeAccent("cyan"),
  emerald: makeAccent("emerald"),
  green: makeAccent("green"),
  indigo: makeAccent("indigo"),
  lime: makeAccent("lime"),
  orange: makeAccent("orange"),
  pink: makeAccent("pink"),
  purple: makeAccent("purple"),
  red: makeAccent("red"),
  rose: makeAccent("rose"),
  sky: makeAccent("sky"),
  slate: makeAccent("slate"),
  stone: makeAccent("stone"),
  teal: makeAccent("teal"),
  violet: makeAccent("violet"),
  yellow: makeAccent("yellow"),
  zinc: makeAccent("zinc"),
};

function accentFor(colorName: string) {
  return ACCENTS[colorName] ?? ACCENTS.slate;
}

/* ── Cover layout ──────────────────────────────────────── */

function CoverLayout({
  colorName,
  icon: Icon,
  badge,
  title,
  subtitle,
  compact,
}: {
  colorName: string;
  icon: LucideIcon;
  badge: string;
  title?: string;
  subtitle?: string;
  compact?: boolean;
  topRight?: React.ReactNode;
}) {
  const a = accentFor(colorName);

  if (compact) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-100 dark:bg-slate-900/40">
        <Icon size={17} strokeWidth={2} className={a.muted} />
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "relative flex h-full w-full flex-col overflow-hidden",
        a.shell,
      )}
    >
      {/* Centered icon */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="relative">
          <Icon
            size={42}
            strokeWidth={1.1}
            className={clsx("relative opacity-[0.18]", a.muted)}
          />
        </div>
      </div>

      {/* Header */}
      <div className="relative z-10 flex items-center justify-between px-3 pt-2.5">
        <span
          className={clsx(
            "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold tracking-wide ring-1",
            a.badge,
          )}
        >
          {badge}
        </span>
      </div>

      {/* Footer */}
      <div className="relative z-10 mt-auto px-3 pb-3">
        {title && (
          <p className="truncate text-[13px] font-semibold leading-tight tracking-tight">
            {title}
          </p>
        )}
        {subtitle && (
          <p className="mt-0.5 truncate text-[10px] leading-3 opacity-40">
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
  const a = accentFor(p.colorName);
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge="Markdown"
      title={p.title}
      subtitle={p.subtitle}
      compact={compact}
      topRight={
        p.language && (
          <span className={clsx("text-[10px]", a.muted)}>{p.language}</span>
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
      title={p.title}
      subtitle={p.subtitle}
      compact={compact}
      topRight={
        <div className="flex gap-1">
          <span className="h-[6px] w-[6px] rounded-full bg-current/15" />
          <span className="h-[6px] w-[6px] rounded-full bg-current/10" />
          <span className="h-[6px] w-[6px] rounded-full bg-current/[0.07]" />
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
  const a = accentFor(p.colorName);
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge={p.badge}
      compact={compact}
      topRight={
        <span className={clsx("flex items-center gap-1 text-[10px]", a.muted)}>
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
  const a = accentFor(p.colorName);
  return (
    <CoverLayout
      colorName={p.colorName}
      icon={icon}
      badge={p.badge}
      compact={compact}
      topRight={<Braces size={12} className={clsx("opacity-35", a.muted)} />}
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
