/**
 * File type mapping configuration
 * Contains mappings for file extensions to icons, colors, and categories
 */

import {
  FileCode,
  Image as ImageIcon,
  FileText,
  FileVideo,
  FileAudio,
  FileArchive,
  FileSpreadsheet,
  FileCog,
  FileJson,
  FileType,
  Braces,
  Terminal,
  Database,
  Palette,
  Globe,
  Lock,
  TestTube,
  Blocks,
  Music,
  Film,
  Presentation,
  BookOpen,
  StickyNote,
  File,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { defaultStyles, Type } from "react-file-icon";

export { defaultStyles };
export type { Type };

// ============================================================================
// Unified File Type System - 统一的文件类型图标系统
// ============================================================================

export interface FileTypeInfo {
  icon: LucideIcon;
  color: string;
  bg: string;
  label: string;
  category:
    | "image"
    | "video"
    | "audio"
    | "code"
    | "document"
    | "spreadsheet"
    | "presentation"
    | "archive"
    | "config"
    | "data"
    | "font"
    | "other";
}

// 预定义的样式配置
const STYLES = {
  // 图片样式
  image: {
    emerald: {
      icon: ImageIcon,
      color: "text-emerald-600 dark:text-emerald-400",
      bg: "bg-emerald-100 dark:bg-emerald-900/40",
    },
    pink: {
      icon: ImageIcon,
      color: "text-pink-600 dark:text-pink-400",
      bg: "bg-pink-100 dark:bg-pink-900/40",
    },
    purple: {
      icon: ImageIcon,
      color: "text-purple-600 dark:text-purple-400",
      bg: "bg-purple-100 dark:bg-purple-900/40",
    },
    cyan: {
      icon: ImageIcon,
      color: "text-cyan-600 dark:text-cyan-400",
      bg: "bg-cyan-100 dark:bg-cyan-900/40",
    },
    orange: {
      icon: ImageIcon,
      color: "text-orange-600 dark:text-orange-400",
      bg: "bg-orange-100 dark:bg-orange-900/40",
    },
    amber: {
      icon: ImageIcon,
      color: "text-amber-600 dark:text-amber-400",
      bg: "bg-amber-100 dark:bg-amber-900/40",
    },
    teal: {
      icon: ImageIcon,
      color: "text-teal-600 dark:text-teal-400",
      bg: "bg-teal-100 dark:bg-teal-900/40",
    },
    indigo: {
      icon: ImageIcon,
      color: "text-indigo-600 dark:text-indigo-400",
      bg: "bg-indigo-100 dark:bg-indigo-900/40",
    },
    rose: {
      icon: ImageIcon,
      color: "text-rose-600 dark:text-rose-400",
      bg: "bg-rose-100 dark:bg-rose-900/40",
    },
    violet: {
      icon: ImageIcon,
      color: "text-violet-600 dark:text-violet-400",
      bg: "bg-violet-100 dark:bg-violet-900/40",
    },
  },
  // 通用代码样式
  code: {
    yellow: {
      icon: FileCode,
      color: "text-yellow-600 dark:text-yellow-400",
      bg: "bg-yellow-100 dark:bg-yellow-900/40",
    },
    blue: {
      icon: FileCode,
      color: "text-blue-600 dark:text-blue-400",
      bg: "bg-blue-100 dark:bg-blue-900/40",
    },
    sky: {
      icon: FileCode,
      color: "text-sky-600 dark:text-sky-400",
      bg: "bg-sky-100 dark:bg-sky-900/40",
    },
    red: {
      icon: FileCode,
      color: "text-red-600 dark:text-red-400",
      bg: "bg-red-100 dark:bg-red-900/40",
    },
    purple: {
      icon: FileCode,
      color: "text-purple-600 dark:text-purple-400",
      bg: "bg-purple-100 dark:bg-purple-900/40",
    },
    orange: {
      icon: FileCode,
      color: "text-orange-600 dark:text-orange-400",
      bg: "bg-orange-100 dark:bg-orange-900/40",
    },
    cyan: {
      icon: FileCode,
      color: "text-cyan-600 dark:text-cyan-400",
      bg: "bg-cyan-100 dark:bg-cyan-900/40",
    },
    green: {
      icon: FileCode,
      color: "text-green-600 dark:text-green-400",
      bg: "bg-green-100 dark:bg-green-900/40",
    },
    indigo: {
      icon: FileCode,
      color: "text-indigo-600 dark:text-indigo-400",
      bg: "bg-indigo-100 dark:bg-indigo-900/40",
    },
    emerald: {
      icon: FileCode,
      color: "text-emerald-600 dark:text-emerald-400",
      bg: "bg-emerald-100 dark:bg-emerald-900/40",
    },
  },
} as const;

// 扩展名到配置的映射（使用数组表示同配置的扩展名）
type ExtConfig = { ext: string | string[] } & Omit<FileTypeInfo, "icon"> & {
    icon: LucideIcon;
  };

const createTypeMap = (configs: ExtConfig[]): Record<string, FileTypeInfo> => {
  const map: Record<string, FileTypeInfo> = {};
  for (const { ext, ...info } of configs) {
    const exts = Array.isArray(ext) ? ext : [ext];
    for (const e of exts) {
      map[e] = info as FileTypeInfo;
    }
  }
  return map;
};

// 文件类型配置
const FILE_TYPE_CONFIGS: ExtConfig[] = [
  // ===== 图片 =====
  {
    ext: ["jpg", "jpeg"],
    ...STYLES.image.emerald,
    label: "JPEG",
    category: "image",
  },
  { ext: "png", ...STYLES.image.pink, label: "PNG", category: "image" },
  { ext: "gif", ...STYLES.image.purple, label: "GIF", category: "image" },
  { ext: "webp", ...STYLES.image.cyan, label: "WebP", category: "image" },
  { ext: "svg", ...STYLES.image.orange, label: "SVG", category: "image" },
  { ext: "ico", ...STYLES.image.amber, label: "ICO", category: "image" },
  { ext: "bmp", ...STYLES.image.teal, label: "BMP", category: "image" },
  {
    ext: ["tiff", "tif"],
    ...STYLES.image.indigo,
    label: "TIFF",
    category: "image",
  },
  { ext: "heic", ...STYLES.image.rose, label: "HEIC", category: "image" },
  { ext: "heif", ...STYLES.image.rose, label: "HEIF", category: "image" },
  { ext: "avif", ...STYLES.image.violet, label: "AVIF", category: "image" },

  // ===== 视频 =====
  {
    ext: "mp4",
    icon: Film,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "MP4",
    category: "video",
  },
  {
    ext: "mov",
    icon: FileVideo,
    color: "text-sky-600 dark:text-sky-400",
    bg: "bg-sky-100 dark:bg-sky-900/40",
    label: "MOV",
    category: "video",
  },
  {
    ext: "avi",
    icon: FileVideo,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "AVI",
    category: "video",
  },
  {
    ext: "mkv",
    icon: FileVideo,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "MKV",
    category: "video",
  },
  {
    ext: "webm",
    icon: FileVideo,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "WebM",
    category: "video",
  },
  {
    ext: "wmv",
    icon: FileVideo,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WMV",
    category: "video",
  },
  {
    ext: "flv",
    icon: FileVideo,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "FLV",
    category: "video",
  },
  {
    ext: "m4v",
    icon: FileVideo,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "M4V",
    category: "video",
  },
  {
    ext: ["mpeg", "mpg"],
    icon: FileVideo,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "MPEG",
    category: "video",
  },
  {
    ext: "3gp",
    icon: FileVideo,
    color: "text-lime-600 dark:text-lime-400",
    bg: "bg-lime-100 dark:bg-lime-900/40",
    label: "3GP",
    category: "video",
  },

  // ===== 音频 =====
  {
    ext: "mp3",
    icon: Music,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "MP3",
    category: "audio",
  },
  {
    ext: "wav",
    icon: FileAudio,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WAV",
    category: "audio",
  },
  {
    ext: "flac",
    icon: FileAudio,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "FLAC",
    category: "audio",
  },
  {
    ext: "aac",
    icon: FileAudio,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "AAC",
    category: "audio",
  },
  {
    ext: "ogg",
    icon: FileAudio,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "OGG",
    category: "audio",
  },
  {
    ext: "wma",
    icon: FileAudio,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "WMA",
    category: "audio",
  },
  {
    ext: "m4a",
    icon: FileAudio,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "M4A",
    category: "audio",
  },
  {
    ext: "aiff",
    icon: FileAudio,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "AIFF",
    category: "audio",
  },
  {
    ext: "opus",
    icon: FileAudio,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "Opus",
    category: "audio",
  },

  // ===== JavaScript/TypeScript =====
  {
    ext: ["js", "mjs", "cjs"],
    ...STYLES.code.yellow,
    label: "JavaScript",
    category: "code",
  },
  { ext: "ts", ...STYLES.code.blue, label: "TypeScript", category: "code" },
  { ext: ["jsx", "tsx"], ...STYLES.code.sky, label: "JSX", category: "code" },

  // ===== Python =====
  {
    ext: ["py", "pyw"],
    ...STYLES.code.blue,
    label: "Python",
    category: "code",
  },
  { ext: "pyx", ...STYLES.code.orange, label: "Cython", category: "code" },

  // ===== Web =====
  {
    ext: ["html", "htm"],
    icon: Globe,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "HTML",
    category: "code",
  },
  {
    ext: "css",
    icon: Palette,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "CSS",
    category: "code",
  },
  {
    ext: ["scss", "sass"],
    icon: Palette,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "SCSS",
    category: "code",
  },
  {
    ext: "less",
    icon: Palette,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "Less",
    category: "code",
  },

  // ===== 其他语言 =====
  { ext: "java", ...STYLES.code.red, label: "Java", category: "code" },
  {
    ext: ["kt", "kts"],
    ...STYLES.code.purple,
    label: "Kotlin",
    category: "code",
  },
  { ext: "swift", ...STYLES.code.orange, label: "Swift", category: "code" },
  { ext: "go", ...STYLES.code.cyan, label: "Go", category: "code" },
  { ext: "rs", ...STYLES.code.orange, label: "Rust", category: "code" },
  { ext: "rb", ...STYLES.code.red, label: "Ruby", category: "code" },
  { ext: "php", ...STYLES.code.indigo, label: "PHP", category: "code" },
  {
    ext: ["c", "cpp", "cc", "cxx"],
    ...STYLES.code.blue,
    label: "C++",
    category: "code",
  },
  {
    ext: ["h", "hpp"],
    ...STYLES.code.purple,
    label: "Header",
    category: "code",
  },
  { ext: "cs", ...STYLES.code.purple, label: "C#", category: "code" },
  { ext: "scala", ...STYLES.code.red, label: "Scala", category: "code" },
  { ext: "lua", ...STYLES.code.blue, label: "Lua", category: "code" },
  { ext: "r", ...STYLES.code.blue, label: "R", category: "code" },
  {
    ext: "sql",
    icon: Database,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "SQL",
    category: "code",
  },

  // ===== 框架 =====
  { ext: "vue", ...STYLES.code.emerald, label: "Vue", category: "code" },
  { ext: "svelte", ...STYLES.code.orange, label: "Svelte", category: "code" },
  { ext: "astro", ...STYLES.code.orange, label: "Astro", category: "code" },

  // ===== 脚本 =====
  {
    ext: ["sh", "bash", "zsh", "fish"],
    icon: Terminal,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Shell",
    category: "code",
  },
  {
    ext: "ps1",
    icon: Terminal,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "PowerShell",
    category: "code",
  },
  {
    ext: "bat",
    icon: Terminal,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "Batch",
    category: "code",
  },

  // ===== 数据文件 =====
  {
    ext: ["json", "jsonc", "json5"],
    icon: FileJson,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "JSON",
    category: "data",
  },
  {
    ext: "xml",
    icon: Braces,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "XML",
    category: "data",
  },
  {
    ext: ["yaml", "yml"],
    icon: Braces,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "YAML",
    category: "data",
  },
  {
    ext: "toml",
    icon: Braces,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "TOML",
    category: "data",
  },
  {
    ext: "csv",
    icon: FileSpreadsheet,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "CSV",
    category: "data",
  },
  {
    ext: "tsv",
    icon: FileSpreadsheet,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "TSV",
    category: "data",
  },

  // ===== 配置文件 =====
  {
    ext: ["env", "lock"],
    icon: Lock,
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "Env",
    category: "config",
  },
  {
    ext: ["ini", "cfg", "conf", "config"],
    icon: FileCog,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "Config",
    category: "config",
  },

  // ===== 文档 =====
  {
    ext: "pdf",
    icon: FileText,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "PDF",
    category: "document",
  },
  {
    ext: ["doc", "docx"],
    icon: FileText,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Word",
    category: "document",
  },
  {
    ext: "rtf",
    icon: FileText,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "RTF",
    category: "document",
  },
  {
    ext: "odt",
    icon: FileText,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "ODT",
    category: "document",
  },

  // ===== Markdown =====
  {
    ext: ["md", "markdown"],
    icon: BookOpen,
    color: "text-slate-600 dark:text-slate-400",
    bg: "bg-slate-100 dark:bg-slate-900/40",
    label: "Markdown",
    category: "document",
  },
  {
    ext: "mdx",
    icon: BookOpen,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "MDX",
    category: "document",
  },
  {
    ext: "rst",
    icon: BookOpen,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "reStructuredText",
    category: "document",
  },
  {
    ext: "txt",
    icon: StickyNote,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "Text",
    category: "document",
  },
  {
    ext: "log",
    icon: StickyNote,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "Log",
    category: "document",
  },

  // ===== 电子表格 =====
  {
    ext: ["xls", "xlsx"],
    icon: FileSpreadsheet,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Excel",
    category: "spreadsheet",
  },
  {
    ext: "ods",
    icon: FileSpreadsheet,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "ODS",
    category: "spreadsheet",
  },

  // ===== 演示文稿 =====
  {
    ext: ["ppt", "pptx"],
    icon: Presentation,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "PowerPoint",
    category: "presentation",
  },
  {
    ext: "odp",
    icon: Presentation,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "ODP",
    category: "presentation",
  },
  {
    ext: "key",
    icon: Presentation,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Keynote",
    category: "presentation",
  },

  // ===== 压缩包 =====
  {
    ext: "zip",
    icon: FileArchive,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "ZIP",
    category: "archive",
  },
  {
    ext: "rar",
    icon: FileArchive,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "RAR",
    category: "archive",
  },
  {
    ext: "7z",
    icon: FileArchive,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "7-Zip",
    category: "archive",
  },
  {
    ext: ["tar", "gz"],
    icon: FileArchive,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "TAR",
    category: "archive",
  },
  {
    ext: "bz2",
    icon: FileArchive,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "BZIP2",
    category: "archive",
  },
  {
    ext: "xz",
    icon: FileArchive,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "XZ",
    category: "archive",
  },
  {
    ext: ["iso", "dmg", "pkg"],
    icon: FileArchive,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "ISO",
    category: "archive",
  },

  // ===== 可执行文件 =====
  {
    ext: ["exe", "msi"],
    icon: Blocks,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Executable",
    category: "other",
  },
  {
    ext: ["deb", "rpm"],
    icon: Blocks,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "Package",
    category: "other",
  },
  {
    ext: "app",
    icon: Blocks,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "App",
    category: "other",
  },
  {
    ext: "dll",
    icon: Blocks,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "DLL",
    category: "other",
  },
  {
    ext: "so",
    icon: Blocks,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "Shared Lib",
    category: "other",
  },

  // ===== 字体 =====
  {
    ext: "ttf",
    icon: FileType,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "TrueType",
    category: "font",
  },
  {
    ext: "otf",
    icon: FileType,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "OpenType",
    category: "font",
  },
  {
    ext: ["woff", "woff2"],
    icon: FileType,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WOFF",
    category: "font",
  },
  {
    ext: "eot",
    icon: FileType,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-900/40",
    label: "EOT",
    category: "font",
  },

  // ===== 测试 =====
  {
    ext: ["test", "spec"],
    icon: TestTube,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "Test",
    category: "code",
  },

  // ===== Excalidraw =====
  {
    ext: ["excalidraw", "exdraw"],
    icon: Blocks,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "Excalidraw",
    category: "document",
  },
];

// 生成文件类型映射
export const FILE_TYPE_MAP = createTypeMap(FILE_TYPE_CONFIGS);

// MIME 类型到扩展名的映射
export const MIME_TO_EXT: Record<string, string> = {
  // 图片
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/svg+xml": "svg",
  "image/bmp": "bmp",
  "image/tiff": "tiff",
  "image/x-icon": "ico",
  "image/heic": "heic",
  "image/heif": "heif",
  "image/avif": "avif",
  // 视频
  "video/mp4": "mp4",
  "video/quicktime": "mov",
  "video/x-msvideo": "avi",
  "video/x-matroska": "mkv",
  "video/webm": "webm",
  "video/x-ms-wmv": "wmv",
  "video/x-flv": "flv",
  "video/x-m4v": "m4v",
  "video/mpeg": "mpeg",
  "video/3gpp": "3gp",
  // 音频
  "audio/mpeg": "mp3",
  "audio/wav": "wav",
  "audio/flac": "flac",
  "audio/aac": "aac",
  "audio/ogg": "ogg",
  "audio/x-ms-wma": "wma",
  "audio/mp4": "m4a",
  "audio/aiff": "aiff",
  "audio/opus": "opus",
  // 代码
  "text/javascript": "js",
  "application/javascript": "js",
  "text/typescript": "ts",
  "application/typescript": "ts",
  "text/html": "html",
  "text/css": "css",
  "text/x-python": "py",
  "text/x-java-source": "java",
  "text/x-c": "c",
  "text/x-c++": "cpp",
  "text/x-go": "go",
  "text/x-rust": "rs",
  "text/x-ruby": "rb",
  "text/x-php": "php",
  "text/x-sh": "sh",
  "application/x-sh": "sh",
  // 数据
  "application/json": "json",
  "text/json": "json",
  "application/xml": "xml",
  "text/xml": "xml",
  "text/yaml": "yaml",
  "application/x-yaml": "yaml",
  "text/csv": "csv",
  "text/tab-separated-values": "tsv",
  // 文档
  "application/pdf": "pdf",
  "application/msword": "doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "docx",
  "application/rtf": "rtf",
  "text/markdown": "md",
  "text/plain": "txt",
  "text/x-log": "log",
  // 电子表格
  "application/vnd.ms-excel": "xls",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
  "application/vnd.oasis.opendocument.spreadsheet": "ods",
  // 演示文稿
  "application/vnd.ms-powerpoint": "ppt",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation":
    "pptx",
  "application/vnd.oasis.opendocument.presentation": "odp",
  // 压缩包
  "application/zip": "zip",
  "application/x-rar-compressed": "rar",
  "application/x-7z-compressed": "7z",
  "application/x-tar": "tar",
  "application/gzip": "gz",
  "application/x-bzip2": "bz2",
  "application/x-xz": "xz",
  "application/x-iso9660-image": "iso",
  "application/x-apple-diskimage": "dmg",
  // 字体
  "font/ttf": "ttf",
  "font/otf": "otf",
  "font/woff": "woff",
  "font/woff2": "woff2",
};

// 默认文件类型
export const DEFAULT_FILE_TYPE: FileTypeInfo = {
  icon: File,
  color: "text-stone-500 dark:text-stone-400",
  bg: "bg-stone-100 dark:bg-stone-800",
  label: "File",
  category: "other",
};
