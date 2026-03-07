/**
 * File type checking utilities
 * Functions to check file types based on extension
 */

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

// Check if file is PowerPoint presentation (any format)
export function isPptFile(ext: string): boolean {
  return ext === "ppt" || ext === "pptx";
}

// Check if file is PowerPoint Open XML format (.pptx)
export function isPptxFile(ext: string): boolean {
  return ext === "pptx";
}

// Check if file is legacy PowerPoint format (.ppt)
export function isLegacyPptFile(ext: string): boolean {
  return ext === "ppt";
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
