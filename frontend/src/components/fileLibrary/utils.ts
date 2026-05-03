import type { RevealedFileItem } from "../../services/api";
import { formatFileSize, getFileTypeInfo } from "../documents/utils";

/* ── Time formatting ──────────────────────────────────── */

export function formatTimeAgo(
  t: (key: string, opts?: Record<string, unknown>) => string,
  isoString: string,
): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return t("fileLibrary.timeAgo.justNow");
  if (diffMin < 60)
    return t("fileLibrary.timeAgo.minutesAgo", { count: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return t("fileLibrary.timeAgo.hoursAgo", { count: diffHr });
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return t("fileLibrary.timeAgo.daysAgo", { count: diffDay });
  return t("fileLibrary.timeAgo.monthsAgo", {
    count: Math.floor(diffDay / 30),
  });
}

/* ── File extension ───────────────────────────────────── */

export function getExt(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx > 0 ? name.slice(idx + 1).toUpperCase() : "";
}

/* ── Build metadata line ──────────────────────────────── */

export function buildMeta(
  file: RevealedFileItem,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const isProject = file.file_type === "project";
  const ext = isProject ? "" : getExt(file.file_name);
  const parts: string[] = [];
  if (!isProject && file.file_size > 0)
    parts.push(formatFileSize(file.file_size));
  if (ext) parts.push(ext);
  parts.push(formatTimeAgo(t, file.created_at));
  return parts.join(" \u00B7 ");
}

export function getSessionNavigationTarget(
  files: RevealedFileItem[],
): RevealedFileItem | null {
  return files[0] ?? null;
}

export type FileCardPreviewKind =
  | "image"
  | "text"
  | "code"
  | "markdown"
  | "project"
  | "document"
  | "fallback";

export type FileCardPreviewTone =
  | "blue"
  | "green"
  | "amber"
  | "rose"
  | "violet"
  | "stone";

export interface FileCardPreview {
  kind: FileCardPreviewKind;
  title: string;
  subtitle: string;
  badge: string;
  lines: string[];
  tone: FileCardPreviewTone;
  imageUrl?: string;
}

const CODE_EXTENSIONS = new Set([
  "BASH",
  "C",
  "CPP",
  "CSS",
  "GO",
  "H",
  "INI",
  "JAVA",
  "JS",
  "JSX",
  "PHP",
  "PY",
  "RB",
  "RS",
  "SH",
  "SQL",
  "TS",
  "TSX",
  "VUE",
  "YAML",
  "YML",
  "ZSH",
]);

const DATA_EXTENSIONS = new Set(["CSV", "JSON", "TOML", "XML"]);

function stripExtension(fileName: string): string {
  const last = fileName.split("/").pop() || fileName;
  const idx = last.lastIndexOf(".");
  return idx > 0 ? last.slice(0, idx) : last;
}

function compactLine(value: string | null | undefined): string {
  return (value || "").replace(/\s+/g, " ").trim();
}

function normalizeLines(lines: Array<string | null | undefined>): string[] {
  return lines.map(compactLine).filter(Boolean).slice(0, 4);
}

function formatCount(count: number | undefined): string {
  if (!count || count < 1) return "Project files";
  return count === 1 ? "1 file" : `${count} files`;
}

function normalizeStoredPreview(
  file: RevealedFileItem,
): FileCardPreview | null {
  const stored = file.card_preview;
  if (!stored) return null;

  const ext = getExt(file.file_name);
  const title = compactLine(stored.title) || stripExtension(file.file_name);
  const subtitle =
    compactLine(stored.subtitle) ||
    compactLine(file.description) ||
    getFileTypeInfo(file.file_name, file.mime_type || undefined).label;
  const textLines =
    Array.isArray(stored.lines) && stored.lines.length > 0
      ? stored.lines
      : (stored.text || "").split("\n");

  return {
    kind: stored.kind || "fallback",
    title,
    subtitle,
    badge: compactLine(stored.badge) || ext || stored.kind.toUpperCase(),
    lines: normalizeLines(textLines),
    tone: normalizeTone(stored.accent),
    imageUrl: stored.image_url || undefined,
  };
}

function normalizeTone(value: string | null | undefined): FileCardPreviewTone {
  if (
    value === "blue" ||
    value === "green" ||
    value === "amber" ||
    value === "rose" ||
    value === "violet" ||
    value === "stone"
  ) {
    return value;
  }
  return "stone";
}

export function buildFileCardPreview(file: RevealedFileItem): FileCardPreview {
  const stored = normalizeStoredPreview(file);
  if (stored) return stored;

  const fileInfo = getFileTypeInfo(file.file_name, file.mime_type || undefined);
  const ext = getExt(file.file_name);
  const title = stripExtension(file.file_name);
  const description = compactLine(file.description);

  if (file.file_type === "image" && file.url) {
    return {
      kind: "image",
      title,
      subtitle: description || fileInfo.label,
      badge: ext || "IMG",
      lines: [],
      tone: "green",
      imageUrl: file.url,
    };
  }

  if (file.file_type === "project") {
    const meta = file.project_meta;
    const template = (meta?.template || "project").toUpperCase();
    const fileCount =
      meta?.file_count ??
      (meta?.files ? Object.keys(meta.files).length : undefined);
    const subtitle = formatCount(fileCount);
    return {
      kind: "project",
      title,
      subtitle,
      badge: template,
      lines: normalizeLines([
        meta?.entry ? `Entry ${meta.entry}` : "Entry auto detected",
        fileCount ? `${subtitle} indexed` : "Files indexed",
        description,
      ]),
      tone: "violet",
    };
  }

  if (ext === "MD" || ext === "MARKDOWN") {
    return {
      kind: "markdown",
      title,
      subtitle: description || "Markdown document",
      badge: "MD",
      lines: normalizeLines([`# ${title}`, description, "Preview ready"]),
      tone: "blue",
    };
  }

  if (CODE_EXTENSIONS.has(ext)) {
    return {
      kind: "code",
      title,
      subtitle: description || `${ext || fileInfo.label} source file`,
      badge: ext || "CODE",
      lines: normalizeLines([
        description && `// ${description}`,
        `const file = "${file.file_name}";`,
        "export default file;",
      ]),
      tone: "green",
    };
  }

  if (DATA_EXTENSIONS.has(ext)) {
    return {
      kind: "text",
      title,
      subtitle: description || `${ext} data file`,
      badge: ext,
      lines: normalizeLines([
        description,
        "{",
        `  "name": "${file.file_name}"`,
        "}",
      ]),
      tone: "amber",
    };
  }

  return {
    kind: file.file_type === "document" ? "document" : "fallback",
    title,
    subtitle: description || fileInfo.label,
    badge: ext || fileInfo.label.toUpperCase(),
    lines: normalizeLines([
      description,
      file.file_size > 0 ? formatFileSize(file.file_size) : "",
      file.mime_type || fileInfo.label,
    ]),
    tone: file.file_type === "video" ? "rose" : "stone",
  };
}
