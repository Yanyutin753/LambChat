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
  File,
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
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { defaultStyles, Type } from "react-file-icon";

// Re-export react-file-icon for convenience
export { defaultStyles };
export type { Type };

// Get file extension
export function getFileExtension(fileName: string): string {
  return fileName.split(".").pop()?.toLowerCase() || "";
}

// Check if file is binary (video, audio, archive, etc.)
export function isBinaryFile(ext: string): boolean {
  return (
    isVideoFile(ext) ||
    isAudioFile(ext) ||
    isArchiveFile(ext) ||
    isExecutableFile(ext)
  );
}

// Check if file is video
export function isVideoFile(ext: string): boolean {
  const videoExts = [
    "mp4",
    "avi",
    "mov",
    "wmv",
    "mkv",
    "webm",
    "flv",
    "m4v",
    "mpeg",
    "mpg",
  ];
  return videoExts.includes(ext);
}

// Check if file is audio
export function isAudioFile(ext: string): boolean {
  const audioExts = [
    "mp3",
    "wav",
    "ogg",
    "flac",
    "aac",
    "m4a",
    "wma",
    "aiff",
    "opus",
  ];
  return audioExts.includes(ext);
}

// Check if file is archive
export function isArchiveFile(ext: string): boolean {
  const archiveExts = [
    "zip",
    "rar",
    "7z",
    "tar",
    "gz",
    "bz2",
    "xz",
    "iso",
    "dmg",
  ];
  return archiveExts.includes(ext);
}

// Check if file is executable
export function isExecutableFile(ext: string): boolean {
  const execExts = ["exe", "dll", "so", "app", "dmg", "deb", "rpm", "msi"];
  return execExts.includes(ext);
}

// Check if file is an image
export function isImageFile(ext: string): boolean {
  const imageExts = ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp", "ico"];
  return imageExts.includes(ext);
}

// Check if file is PDF
export function isPdfFile(ext: string): boolean {
  return ext === "pdf";
}

// Check if file is Word document
export function isWordFile(ext: string): boolean {
  const wordExts = ["doc", "docx"];
  return wordExts.includes(ext);
}

// Check if file is Excel spreadsheet
export function isExcelFile(ext: string): boolean {
  const excelExts = ["xls", "xlsx", "csv"];
  return excelExts.includes(ext);
}

// Check if file is PowerPoint presentation
export function isPptFile(ext: string): boolean {
  const pptExts = ["ppt", "pptx"];
  return pptExts.includes(ext);
}

// Check if file is HTML
export function isHtmlFile(ext: string): boolean {
  return ext === "html" || ext === "htm";
}

// Check if file type is supported for preview
export function isPreviewableFile(ext: string): boolean {
  return (
    isImageFile(ext) ||
    isPdfFile(ext) ||
    isWordFile(ext) ||
    isExcelFile(ext) ||
    isPptFile(ext) ||
    isHtmlFile(ext) ||
    isCodeFile(ext) ||
    isMarkdownFile(ext) ||
    isExcalidrawFile(ext)
  );
}

// Check if file is code
export function isCodeFile(ext: string): boolean {
  const codeExts = [
    "js",
    "ts",
    "py",
    "java",
    "cpp",
    "c",
    "h",
    "css",
    "json",
    "xml",
    "md",
    "txt",
    "tsx",
    "jsx",
    "vue",
    "go",
    "rs",
    "rb",
    "php",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "sh",
    "bash",
    "zsh",
  ];
  return codeExts.includes(ext);
}

// Check if file is markdown
export function isMarkdownFile(fileName: string): boolean {
  const ext = getFileExtension(fileName);
  return ext === "md" || ext === "markdown";
}

// Check if file is Excalidraw
export function isExcalidrawFile(ext: string): boolean {
  return ext === "excalidraw" || ext === "exdraw";
}

// Get file type for react-file-icon
export function getFileIconType(ext: string): string | undefined {
  const typeMap: Record<string, string> = {
    // Code
    js: "js",
    ts: "ts",
    py: "python",
    java: "java",
    cpp: "cpp",
    c: "c",
    h: "c",
    css: "css",
    html: "html",
    json: "json",
    xml: "xml",
    md: "markdown",
    yaml: "yaml",
    yml: "yaml",
    go: "go",
    rs: "rust",
    rb: "ruby",
    php: "php",
    vue: "vue",
    // Documents
    pdf: "pdf",
    doc: "doc",
    docx: "doc",
    xls: "xls",
    xlsx: "xls",
    ppt: "ppt",
    pptx: "ppt",
    // Media
    jpg: "image",
    jpeg: "image",
    png: "image",
    gif: "image",
    svg: "image",
    webp: "image",
    mp4: "video",
    avi: "video",
    mov: "video",
    mp3: "audio",
    wav: "audio",
    // Archives
    zip: "zip",
    rar: "rar",
    "7z": "7z",
    tar: "tar",
    gz: "gz",
    // Text
    txt: "txt",
    log: "log",
  };
  return typeMap[ext];
}

// Get file type info (icon, color, bg)
export function getFileTypeColor(fileName: string): {
  icon: LucideIcon;
  color: string;
  bg: string;
} {
  const ext = getFileExtension(fileName);

  // 图片
  if (["jpg", "jpeg", "png", "gif", "svg", "webp", "ico"].includes(ext)) {
    return {
      icon: ImageIcon,
      color: "text-green-600 dark:text-green-400",
      bg: "bg-green-100 dark:bg-green-900/30",
    };
  }
  // 代码文件
  if (
    [
      "js",
      "ts",
      "jsx",
      "tsx",
      "py",
      "java",
      "cpp",
      "c",
      "h",
      "go",
      "rs",
      "rb",
      "php",
      "vue",
      "html",
      "css",
      "json",
      "xml",
      "yaml",
      "yml",
      "sh",
      "bash",
    ].includes(ext)
  ) {
    return {
      icon: FileCode,
      color: "text-blue-600 dark:text-blue-400",
      bg: "bg-blue-100 dark:bg-blue-900/30",
    };
  }
  // Markdown
  if (["md", "markdown"].includes(ext)) {
    return {
      icon: FileText,
      color: "text-purple-600 dark:text-purple-400",
      bg: "bg-purple-100 dark:bg-purple-900/30",
    };
  }
  // PDF
  if (ext === "pdf") {
    return {
      icon: FileText,
      color: "text-red-600 dark:text-red-400",
      bg: "bg-red-100 dark:bg-red-900/30",
    };
  }
  // 默认文件
  return {
    icon: FileText,
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-100 dark:bg-stone-800",
  };
}

// Detect language for syntax highlighting
export function detectLanguage(fileName: string): string {
  const ext = getFileExtension(fileName);
  const langMap: Record<string, string> = {
    js: "javascript",
    ts: "typescript",
    tsx: "tsx",
    jsx: "jsx",
    py: "python",
    java: "java",
    cpp: "cpp",
    c: "c",
    h: "c",
    css: "css",
    html: "html",
    json: "json",
    xml: "xml",
    md: "markdown",
    yaml: "yaml",
    yml: "yaml",
    go: "go",
    rs: "rust",
    rb: "ruby",
    php: "php",
    sh: "bash",
    bash: "bash",
    zsh: "bash",
    sql: "sql",
    swift: "swift",
    kotlin: "kotlin",
    scala: "scala",
  };
  return langMap[ext] || "plaintext";
}

// ============================================================================
// Unified File Type System - 统一的文件类型图标系统
// ============================================================================

export interface FileTypeInfo {
  /** Lucide 图标组件 */
  icon: LucideIcon;
  /** 图标颜色 class */
  color: string;
  /** 背景颜色 class */
  bg: string;
  /** 文件类型标签 */
  label: string;
  /** 文件分类 */
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

// 文件类型配置映射（基于扩展名）
const FILE_TYPE_MAP: Record<
  string,
  {
    icon: LucideIcon;
    color: string;
    bg: string;
    label: string;
    category: FileTypeInfo["category"];
  }
> = {
  // ===== 图片 =====
  jpg: {
    icon: ImageIcon,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "JPEG",
    category: "image",
  },
  jpeg: {
    icon: ImageIcon,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "JPEG",
    category: "image",
  },
  png: {
    icon: ImageIcon,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "PNG",
    category: "image",
  },
  gif: {
    icon: ImageIcon,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "GIF",
    category: "image",
  },
  webp: {
    icon: ImageIcon,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "WebP",
    category: "image",
  },
  svg: {
    icon: ImageIcon,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "SVG",
    category: "image",
  },
  ico: {
    icon: ImageIcon,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "ICO",
    category: "image",
  },
  bmp: {
    icon: ImageIcon,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "BMP",
    category: "image",
  },
  tiff: {
    icon: ImageIcon,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "TIFF",
    category: "image",
  },
  tif: {
    icon: ImageIcon,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "TIFF",
    category: "image",
  },
  heic: {
    icon: ImageIcon,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "HEIC",
    category: "image",
  },
  heif: {
    icon: ImageIcon,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "HEIF",
    category: "image",
  },
  avif: {
    icon: ImageIcon,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "AVIF",
    category: "image",
  },

  // ===== 视频 =====
  mp4: {
    icon: Film,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "MP4",
    category: "video",
  },
  mov: {
    icon: FileVideo,
    color: "text-sky-600 dark:text-sky-400",
    bg: "bg-sky-100 dark:bg-sky-900/40",
    label: "MOV",
    category: "video",
  },
  avi: {
    icon: FileVideo,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "AVI",
    category: "video",
  },
  mkv: {
    icon: FileVideo,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "MKV",
    category: "video",
  },
  webm: {
    icon: FileVideo,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "WebM",
    category: "video",
  },
  wmv: {
    icon: FileVideo,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WMV",
    category: "video",
  },
  flv: {
    icon: FileVideo,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "FLV",
    category: "video",
  },
  m4v: {
    icon: FileVideo,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "M4V",
    category: "video",
  },
  mpeg: {
    icon: FileVideo,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "MPEG",
    category: "video",
  },
  mpg: {
    icon: FileVideo,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "MPEG",
    category: "video",
  },
  "3gp": {
    icon: FileVideo,
    color: "text-lime-600 dark:text-lime-400",
    bg: "bg-lime-100 dark:bg-lime-900/40",
    label: "3GP",
    category: "video",
  },

  // ===== 音频 =====
  mp3: {
    icon: Music,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "MP3",
    category: "audio",
  },
  wav: {
    icon: FileAudio,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WAV",
    category: "audio",
  },
  flac: {
    icon: FileAudio,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "FLAC",
    category: "audio",
  },
  aac: {
    icon: FileAudio,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "AAC",
    category: "audio",
  },
  ogg: {
    icon: FileAudio,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "OGG",
    category: "audio",
  },
  wma: {
    icon: FileAudio,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "WMA",
    category: "audio",
  },
  m4a: {
    icon: FileAudio,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "M4A",
    category: "audio",
  },
  aiff: {
    icon: FileAudio,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "AIFF",
    category: "audio",
  },
  opus: {
    icon: FileAudio,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "Opus",
    category: "audio",
  },

  // ===== 代码 - JavaScript/TypeScript =====
  js: {
    icon: FileCode,
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "JavaScript",
    category: "code",
  },
  mjs: {
    icon: FileCode,
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "ES Module",
    category: "code",
  },
  cjs: {
    icon: FileCode,
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "CommonJS",
    category: "code",
  },
  ts: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "TypeScript",
    category: "code",
  },
  jsx: {
    icon: FileCode,
    color: "text-sky-600 dark:text-sky-400",
    bg: "bg-sky-100 dark:bg-sky-900/40",
    label: "JSX",
    category: "code",
  },
  tsx: {
    icon: FileCode,
    color: "text-sky-600 dark:text-sky-400",
    bg: "bg-sky-100 dark:bg-sky-900/40",
    label: "TSX",
    category: "code",
  },

  // ===== 代码 - Python =====
  py: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Python",
    category: "code",
  },
  pyw: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Python",
    category: "code",
  },
  pyx: {
    icon: FileCode,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "Cython",
    category: "code",
  },

  // ===== 代码 - Web =====
  html: {
    icon: Globe,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "HTML",
    category: "code",
  },
  htm: {
    icon: Globe,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "HTML",
    category: "code",
  },
  css: {
    icon: Palette,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "CSS",
    category: "code",
  },
  scss: {
    icon: Palette,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "SCSS",
    category: "code",
  },
  sass: {
    icon: Palette,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "Sass",
    category: "code",
  },
  less: {
    icon: Palette,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "Less",
    category: "code",
  },

  // ===== 代码 - 其他语言 =====
  java: {
    icon: FileCode,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "Java",
    category: "code",
  },
  kt: {
    icon: FileCode,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "Kotlin",
    category: "code",
  },
  kts: {
    icon: FileCode,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "Kotlin",
    category: "code",
  },
  swift: {
    icon: FileCode,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "Swift",
    category: "code",
  },
  go: {
    icon: FileCode,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "Go",
    category: "code",
  },
  rs: {
    icon: FileCode,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "Rust",
    category: "code",
  },
  rb: {
    icon: FileCode,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "Ruby",
    category: "code",
  },
  php: {
    icon: FileCode,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "PHP",
    category: "code",
  },
  c: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "C",
    category: "code",
  },
  cpp: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "C++",
    category: "code",
  },
  cc: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "C++",
    category: "code",
  },
  cxx: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "C++",
    category: "code",
  },
  h: {
    icon: FileCode,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "Header",
    category: "code",
  },
  hpp: {
    icon: FileCode,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "Header",
    category: "code",
  },
  cs: {
    icon: FileCode,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "C#",
    category: "code",
  },
  scala: {
    icon: FileCode,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "Scala",
    category: "code",
  },
  lua: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Lua",
    category: "code",
  },
  r: {
    icon: FileCode,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "R",
    category: "code",
  },
  sql: {
    icon: Database,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "SQL",
    category: "code",
  },

  // ===== 框架 =====
  vue: {
    icon: FileCode,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "Vue",
    category: "code",
  },
  svelte: {
    icon: FileCode,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "Svelte",
    category: "code",
  },
  astro: {
    icon: FileCode,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "Astro",
    category: "code",
  },

  // ===== 脚本 =====
  sh: {
    icon: Terminal,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Shell",
    category: "code",
  },
  bash: {
    icon: Terminal,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Bash",
    category: "code",
  },
  zsh: {
    icon: Terminal,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Zsh",
    category: "code",
  },
  fish: {
    icon: Terminal,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Fish",
    category: "code",
  },
  ps1: {
    icon: Terminal,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "PowerShell",
    category: "code",
  },
  bat: {
    icon: Terminal,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "Batch",
    category: "code",
  },

  // ===== 数据文件 =====
  json: {
    icon: FileJson,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "JSON",
    category: "data",
  },
  jsonc: {
    icon: FileJson,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "JSON",
    category: "data",
  },
  json5: {
    icon: FileJson,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "JSON5",
    category: "data",
  },
  xml: {
    icon: Braces,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "XML",
    category: "data",
  },
  yaml: {
    icon: Braces,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "YAML",
    category: "data",
  },
  yml: {
    icon: Braces,
    color: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-100 dark:bg-rose-900/40",
    label: "YAML",
    category: "data",
  },
  toml: {
    icon: Braces,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "TOML",
    category: "data",
  },
  csv: {
    icon: FileSpreadsheet,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "CSV",
    category: "data",
  },
  tsv: {
    icon: FileSpreadsheet,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "TSV",
    category: "data",
  },

  // ===== 配置文件 =====
  env: {
    icon: Lock,
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "Env",
    category: "config",
  },
  ini: {
    icon: FileCog,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "INI",
    category: "config",
  },
  cfg: {
    icon: FileCog,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "Config",
    category: "config",
  },
  conf: {
    icon: FileCog,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "Config",
    category: "config",
  },
  config: {
    icon: FileCog,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "Config",
    category: "config",
  },

  // ===== 文档 =====
  pdf: {
    icon: FileText,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "PDF",
    category: "document",
  },
  doc: {
    icon: FileText,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Word",
    category: "document",
  },
  docx: {
    icon: FileText,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Word",
    category: "document",
  },
  rtf: {
    icon: FileText,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "RTF",
    category: "document",
  },
  odt: {
    icon: FileText,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "ODT",
    category: "document",
  },

  // ===== Markdown =====
  md: {
    icon: BookOpen,
    color: "text-slate-600 dark:text-slate-400",
    bg: "bg-slate-100 dark:bg-slate-900/40",
    label: "Markdown",
    category: "document",
  },
  markdown: {
    icon: BookOpen,
    color: "text-slate-600 dark:text-slate-400",
    bg: "bg-slate-100 dark:bg-slate-900/40",
    label: "Markdown",
    category: "document",
  },
  mdx: {
    icon: BookOpen,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "MDX",
    category: "document",
  },
  rst: {
    icon: BookOpen,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "reStructuredText",
    category: "document",
  },
  txt: {
    icon: StickyNote,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "Text",
    category: "document",
  },
  log: {
    icon: StickyNote,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "Log",
    category: "document",
  },

  // ===== 电子表格 =====
  xls: {
    icon: FileSpreadsheet,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Excel",
    category: "spreadsheet",
  },
  xlsx: {
    icon: FileSpreadsheet,
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-100 dark:bg-green-900/40",
    label: "Excel",
    category: "spreadsheet",
  },
  ods: {
    icon: FileSpreadsheet,
    color: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-100 dark:bg-teal-900/40",
    label: "ODS",
    category: "spreadsheet",
  },

  // ===== 演示文稿 =====
  ppt: {
    icon: Presentation,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "PowerPoint",
    category: "presentation",
  },
  pptx: {
    icon: Presentation,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "PowerPoint",
    category: "presentation",
  },
  odp: {
    icon: Presentation,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "ODP",
    category: "presentation",
  },
  key: {
    icon: Presentation,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Keynote",
    category: "presentation",
  },

  // ===== 压缩包 =====
  zip: {
    icon: FileArchive,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-900/40",
    label: "ZIP",
    category: "archive",
  },
  rar: {
    icon: FileArchive,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "RAR",
    category: "archive",
  },
  "7z": {
    icon: FileArchive,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "7-Zip",
    category: "archive",
  },
  tar: {
    icon: FileArchive,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "TAR",
    category: "archive",
  },
  gz: {
    icon: FileArchive,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-100 dark:bg-orange-900/40",
    label: "GZIP",
    category: "archive",
  },
  bz2: {
    icon: FileArchive,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "BZIP2",
    category: "archive",
  },
  xz: {
    icon: FileArchive,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "XZ",
    category: "archive",
  },
  iso: {
    icon: FileArchive,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "ISO",
    category: "archive",
  },
  dmg: {
    icon: FileArchive,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "DMG",
    category: "archive",
  },
  pkg: {
    icon: FileArchive,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "PKG",
    category: "archive",
  },

  // ===== 可执行文件 =====
  exe: {
    icon: Blocks,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Executable",
    category: "other",
  },
  msi: {
    icon: Blocks,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "Installer",
    category: "other",
  },
  deb: {
    icon: Blocks,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "Debian",
    category: "other",
  },
  rpm: {
    icon: Blocks,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-100 dark:bg-red-900/40",
    label: "RPM",
    category: "other",
  },
  app: {
    icon: Blocks,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "App",
    category: "other",
  },
  dll: {
    icon: Blocks,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "DLL",
    category: "other",
  },
  so: {
    icon: Blocks,
    color: "text-cyan-600 dark:text-cyan-400",
    bg: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "Shared Lib",
    category: "other",
  },

  // ===== 字体 =====
  ttf: {
    icon: FileType,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-900/40",
    label: "TrueType",
    category: "font",
  },
  otf: {
    icon: FileType,
    color: "text-purple-600 dark:text-purple-400",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    label: "OpenType",
    category: "font",
  },
  woff: {
    icon: FileType,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WOFF",
    category: "font",
  },
  woff2: {
    icon: FileType,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    label: "WOFF2",
    category: "font",
  },
  eot: {
    icon: FileType,
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-900/40",
    label: "EOT",
    category: "font",
  },

  // ===== 测试 =====
  test: {
    icon: TestTube,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "Test",
    category: "code",
  },
  spec: {
    icon: TestTube,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "Spec",
    category: "code",
  },

  // ===== 锁文件 =====
  lock: {
    icon: Lock,
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "Lock",
    category: "config",
  },

  // ===== Excalidraw =====
  excalidraw: {
    icon: Blocks,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "Excalidraw",
    category: "document",
  },
  exdraw: {
    icon: Blocks,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-900/40",
    label: "Excalidraw",
    category: "document",
  },
};

// MIME 类型到扩展名的映射
const MIME_TO_EXT: Record<string, string> = {
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
const DEFAULT_FILE_TYPE: FileTypeInfo = {
  icon: File,
  color: "text-stone-500 dark:text-stone-400",
  bg: "bg-stone-100 dark:bg-stone-800",
  label: "File",
  category: "other",
};

/**
 * 获取文件类型信息（统一入口）
 * 支持通过文件名、路径或 MIME 类型获取
 *
 * @param input - 文件名、文件路径或 MIME 类型
 * @param mimeType - 可选的 MIME 类型，优先级更高
 * @returns 文件类型信息
 */
export function getFileTypeInfo(
  input: string,
  mimeType?: string,
): FileTypeInfo {
  // 1. 如果提供了 MIME 类型，优先使用
  if (mimeType) {
    const normalizedMime = mimeType.toLowerCase();
    const ext = MIME_TO_EXT[normalizedMime];
    if (ext && FILE_TYPE_MAP[ext]) {
      return { ...FILE_TYPE_MAP[ext] };
    }

    // MIME 类型通配符匹配
    if (normalizedMime.startsWith("image/")) {
      return { ...FILE_TYPE_MAP.jpg };
    }
    if (normalizedMime.startsWith("video/")) {
      return { ...FILE_TYPE_MAP.mp4 };
    }
    if (normalizedMime.startsWith("audio/")) {
      return { ...FILE_TYPE_MAP.mp3 };
    }
    if (normalizedMime.startsWith("text/")) {
      return { ...FILE_TYPE_MAP.txt };
    }
    if (normalizedMime.includes("json")) {
      return { ...FILE_TYPE_MAP.json };
    }
    if (normalizedMime.includes("xml")) {
      return { ...FILE_TYPE_MAP.xml };
    }
    if (normalizedMime.includes("javascript")) {
      return { ...FILE_TYPE_MAP.js };
    }
  }

  // 2. 从文件名/路径获取扩展名
  const ext = getFileExtension(input);
  if (ext && FILE_TYPE_MAP[ext]) {
    return { ...FILE_TYPE_MAP[ext] };
  }

  // 3. 返回默认值
  return { ...DEFAULT_FILE_TYPE };
}

/**
 * 从 MIME 类型获取文件类型信息
 * @param mimeType - MIME 类型
 * @returns 文件类型信息
 */
export function getFileTypeInfoFromMime(mimeType: string): FileTypeInfo {
  return getFileTypeInfo("", mimeType);
}

/**
 * 从文件名获取文件类型信息
 * @param fileName - 文件名或路径
 * @returns 文件类型信息
 */
export function getFileTypeInfoFromName(fileName: string): FileTypeInfo {
  return getFileTypeInfo(fileName);
}

/**
 * 格式化文件大小
 * @param bytes - 文件大小（字节）
 * @returns 格式化后的文件大小字符串
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
