/**
 * Language detection utilities
 * Detect programming language from file extension
 */

import { FileCode, Image as ImageIcon, FileText } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getFileExtension } from "./fileTypeChecks";

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
