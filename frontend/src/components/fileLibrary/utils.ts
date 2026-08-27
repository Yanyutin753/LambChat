import type { RevealedFileItem } from "../../services/api";
import {
  formatFileSize,
  getFileExtension,
  getFileTypeInfo,
  isExcalidrawFile,
  isImageFile,
} from "../documents/utils";
import { formatTimeAgo } from "../../utils/datetime";
import type { TFunction } from "i18next";

// Re-export for backward compatibility
export { formatTimeAgo };

/* ── File extension ───────────────────────────────────── */

export function getExt(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx > 0 ? name.slice(idx + 1).toUpperCase() : "";
}

/* ── Build metadata line ──────────────────────────────── */

export function buildMeta(file: RevealedFileItem, t: TFunction): string {
  const isProject = file.file_type === "project";
  const ext = isProject ? "" : getExt(file.file_name);
  const parts: string[] = [];
  if (!isProject && file.file_size > 0)
    parts.push(formatFileSize(file.file_size));
  if (ext) parts.push(CODE_LANG_MAP[ext] || ext);
  parts.push(formatTimeAgo(t, file.created_at));
  return parts.join(" · ");
}

export function getSessionNavigationTarget(
  files: RevealedFileItem[],
): RevealedFileItem | null {
  return files[0] ?? null;
}

export function isPreviewableImageFile(file: RevealedFileItem): boolean {
  if (!file.url) return false;
  return (
    file.file_type === "image" || isImageFile(getFileExtension(file.file_name))
  );
}

export function getPreviewableImageFiles(
  sessionGroups: Array<{ files: RevealedFileItem[] }>,
): RevealedFileItem[] {
  return sessionGroups.flatMap((group) =>
    group.files.filter(isPreviewableImageFile),
  );
}

export interface ImagePreviewNavigation {
  current: RevealedFileItem | null;
  previous: RevealedFileItem | null;
  next: RevealedFileItem | null;
  index: number;
  total: number;
}

export function getImagePreviewNavigation(
  files: RevealedFileItem[],
  currentId: string | null | undefined,
): ImagePreviewNavigation {
  const index = currentId
    ? files.findIndex((file) => file.id === currentId)
    : -1;

  return {
    current: index >= 0 ? files[index] : null,
    previous: index > 0 ? files[index - 1] : null,
    next: index >= 0 && index < files.length - 1 ? files[index + 1] : null,
    index,
    total: files.length,
  };
}

export type FileCardPreviewKind =
  | "image"
  | "excalidraw"
  | "text"
  | "code"
  | "markdown"
  | "project"
  | "video"
  | "document"
  | "fallback";

export interface FileCardPreview {
  kind: FileCardPreviewKind;
  title: string;
  subtitle: string;
  badge: string;
  lines: string[];
  colorName: string;
  imageUrl?: string;
  language?: string;
}

/* ── Color name extraction ────────────────────────────── */

/**
 * Extract the Tailwind color name from the icon color class.
 * e.g. "text-blue-600 dark:text-blue-400" → "blue"
 *      "text-slate-600 dark:text-slate-400" → "slate"
 */
function extractColorName(iconColor: string): string {
  const match = iconColor.match(/text-(\w+)-\d/);
  return match ? match[1] : "slate";
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

function formatCount(count: number | undefined, t?: TFunction): string {
  if (!count || count < 1)
    return t ? t("files.projectFiles", "项目文件") : "Project files";
  return count === 1
    ? t
      ? t("files.oneFile", "1 个文件")
      : "1 file"
    : t
      ? t("files.countFiles", "{{count}} 个文件", { count })
      : `${count} files`;
}

function normalizeStoredPreview(
  file: RevealedFileItem,
  t?: TFunction,
): FileCardPreview | null {
  const stored = file.card_preview;
  if (!stored) return null;

  const fileInfo = getFileTypeInfo(file.file_name, file.mime_type || undefined);
  const ext = getExt(file.file_name);
  const title = compactLine(stored.title) || stripExtension(file.file_name);
  const subtitle =
    compactLine(stored.subtitle) ||
    compactLine(file.description) ||
    (t ? t(fileInfo.label, fileInfo.label) : fileInfo.label);
  const textLines =
    Array.isArray(stored.lines) && stored.lines.length > 0
      ? stored.lines
      : (stored.text || "").split("\n");

  return {
    kind: stored.kind || "fallback",
    title,
    subtitle,
    badge:
      compactLine(stored.badge) ||
      CODE_LANG_MAP[ext] ||
      ext ||
      stored.kind.toUpperCase(),
    lines: normalizeLines(textLines),
    colorName: extractColorName(fileInfo.color),
    imageUrl: stored.image_url || undefined,
  };
}

const CODE_LANG_MAP: Record<string, string> = {
  TS: "TypeScript",
  TSX: "TypeScript React",
  JS: "JavaScript",
  JSX: "React",
  PY: "Python",
  GO: "Go",
  RS: "Rust",
  JAVA: "Java",
  C: "C",
  CPP: "C++",
  RB: "Ruby",
  PHP: "PHP",
  CSS: "CSS",
  VUE: "Vue",
  SH: "Shell",
  BASH: "Bash",
  ZSH: "Zsh",
  SQL: "SQL",
  YAML: "YAML",
  YML: "YAML",
  INI: "INI",
  H: "C Header",
  RUST: "Rust",
  MD: "Markdown",
  MARKDOWN: "Markdown",
  CSV: "CSV",
  JSON: "JSON",
  XML: "XML",
  TOML: "TOML",
  PNG: "PNG",
  JPG: "JPEG",
  JPEG: "JPEG",
  GIF: "GIF",
  SVG: "SVG",
  WEBP: "WebP",
  PDF: "PDF",
};

function codeLines(ext: string, name: string, desc: string): string[] {
  const stubName = stripExtension(name);
  switch (ext) {
    case "PY":
      return [
        desc ? `"""${desc}"""` : `# ${stubName}`,
        `class ${camelCase(stubName)}:`,
        `    def __init__(self):`,
        `        self.name = "${stubName}"`,
      ];
    case "TS":
    case "TSX":
      return [
        desc ? `// ${desc}` : `// ${stubName}`,
        `interface Props {`,
        `  name: string;`,
        `}`,
        `export const ${camelCase(stubName)} = () => {};`,
      ];
    case "GO":
      return [
        `package ${camelCase(stubName)}`,
        desc ? `// ${desc}` : "",
        `func main() {`,
        `  fmt.Println("${stubName}")`,
      ];
    case "RS":
      return [
        desc ? `// ${desc}` : "",
        `fn main() {`,
        `    println!("${stubName}");`,
        `}`,
      ];
    case "JAVA":
      return [
        `public class ${pascalCase(stubName)} {`,
        desc ? `  // ${desc}` : `  public static void main(String[] args) {`,
        `  }`,
        `}`,
      ];
    case "SQL":
      return [
        `-- ${desc || stubName}`,
        `SELECT * FROM table`,
        `WHERE status = 'active'`,
        `LIMIT 10;`,
      ];
    case "CSS":
      return [
        desc ? `/* ${desc} */` : `/* ${stubName} */`,
        `.container {`,
        `  display: flex;`,
        `  gap: 1rem;`,
      ];
    default:
      return [
        desc ? `// ${desc}` : `// ${stubName}`,
        `function ${camelCase(stubName)}() {`,
        `  return "${stubName}";`,
        `}`,
      ];
  }
}

function camelCase(s: string): string {
  return s
    .replace(/[-_\s]+(.)?/g, (_, c) => (c ? c.toUpperCase() : ""))
    .replace(/^(.)/, (c) => c.toLowerCase());
}

function pascalCase(s: string): string {
  const cc = camelCase(s);
  return cc.charAt(0).toUpperCase() + cc.slice(1);
}

export function buildFileCardPreview(
  file: RevealedFileItem,
  t?: TFunction,
): FileCardPreview {
  const stored = normalizeStoredPreview(file, t);
  if (stored) return stored;

  const fileInfo = getFileTypeInfo(file.file_name, file.mime_type || undefined);
  const colorName = extractColorName(fileInfo.color);
  const ext = getExt(file.file_name);
  const title = stripExtension(file.file_name);
  const label = t ? t(fileInfo.label, fileInfo.label) : fileInfo.label;
  const description = compactLine(file.description);

  if (file.file_type === "image" && file.url) {
    return {
      kind: "image",
      title,
      subtitle: description || label,
      badge: ext || "Image",
      lines: [],
      colorName,
      imageUrl: file.url,
    };
  }

  if (file.file_type === "video" && file.url) {
    return {
      kind: "video",
      title,
      subtitle: description || label,
      badge: ext || "Video",
      lines: [],
      colorName,
      imageUrl: file.url,
    };
  }

  if (file.url && isExcalidrawFile(getFileExtension(file.file_name))) {
    return {
      kind: "excalidraw" as const,
      title,
      subtitle: description || label,
      badge: ext || "Excalidraw",
      lines: [],
      colorName,
      imageUrl: file.url,
    };
  }

  if (file.file_type === "project") {
    const meta = file.project_meta;
    const template = (meta?.template || "project").toUpperCase();
    const fileCount =
      meta?.file_count ??
      (meta?.files ? Object.keys(meta.files).length : undefined);
    const subtitle = formatCount(fileCount, t);
    const entryLabel = meta?.entry
      ? meta.entry.length > 28
        ? "..." + meta.entry.slice(-25)
        : meta.entry
      : "auto";
    return {
      kind: "project",
      title,
      subtitle,
      badge: template,
      language: `Template · ${template}`,
      lines: normalizeLines([
        `▸ Entry ${entryLabel}`,
        fileCount ? `· ${subtitle} indexed` : "· Files indexed",
        description ? `· ${description}` : "",
      ]),
      colorName,
    };
  }

  if (ext === "MD" || ext === "MARKDOWN") {
    return {
      kind: "markdown",
      title,
      subtitle:
        description ||
        (t?.("documents.markdownDocument") ?? "Markdown document"),
      badge: t?.("documents.markdown") ?? "Markdown",
      language: t?.("documents.markdown") ?? "Markdown",
      lines: normalizeLines([
        title,
        description ||
          (t?.("documents.documentContentPreview") ??
            "Document content preview"),
        description ? t?.("documents.readMore") ?? "Read more →" : "",
      ]),
      colorName,
    };
  }

  if (CODE_EXTENSIONS.has(ext)) {
    return {
      kind: "code",
      title,
      subtitle: CODE_LANG_MAP[ext] || ext,
      badge: CODE_LANG_MAP[ext] || ext,
      lines: normalizeLines(codeLines(ext, file.file_name, description)),
      colorName,
    };
  }

  if (DATA_EXTENSIONS.has(ext)) {
    if (ext === "CSV") {
      return {
        kind: "text",
        title,
        subtitle:
          description || (t?.("documents.csvDataFile") ?? "CSV data file"),
        badge: t?.("documents.csv") ?? "CSV",
        lines: normalizeLines([
          "id, name, value",
          "1, item_a, 42",
          "2, item_b, 87",
        ]),
        colorName,
      };
    }
    return {
      kind: "text",
      title,
      subtitle: description || `${ext} data file`,
      badge: ext,
      lines: normalizeLines([
        "{",
        `  "name": "${stripExtension(file.file_name)}",`,
        `  "type": "${ext.toLowerCase()}"`,
        "}",
      ]),
      colorName,
    };
  }

  return {
    kind: file.file_type === "document" ? "document" : "fallback",
    title,
    subtitle: description || label,
    badge: ext || label.toUpperCase(),
    lines: normalizeLines([
      description,
      file.file_size > 0 ? formatFileSize(file.file_size) : "",
      file.mime_type || label,
    ]),
    colorName,
  };
}
