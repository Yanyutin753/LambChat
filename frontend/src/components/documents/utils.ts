import { FileCode, Image as ImageIcon, FileText } from "lucide-react";
import { LucideIcon } from "lucide-react";
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
    isMarkdownFile(ext)
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
