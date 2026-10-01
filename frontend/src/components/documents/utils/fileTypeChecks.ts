/**
 * File type checking utilities
 * Functions to check file types based on extension
 */

// Get file extension
export function getFileExtension(fileName: string): string {
  return fileName.split(".").pop()?.toLowerCase() || "";
}

// Check if file is binary (video, audio, archive, image, font, etc.)
export function isBinaryFile(ext: string): boolean {
  return (
    isVideoFile(ext) ||
    isAudioFile(ext) ||
    isArchiveFile(ext) ||
    isExecutableFile(ext) ||
    isImageFile(ext) ||
    isFontFile(ext)
  );
}

// Check if file is font
export function isFontFile(ext: string): boolean {
  const fontExts = [
    "ttf",
    "otf",
    "woff",
    "woff2",
    "eot",
    // Apple
    "ttc",
    "dfont",
    // Other
    "pfb",
    "pfa",
  ];
  return fontExts.includes(ext);
}

// Check if file is a document (office suite, PDF, ebook, etc.)
export function isDocumentFile(ext: string): boolean {
  return (
    isPdfFile(ext) ||
    isWordFile(ext) ||
    isExcelFile(ext) ||
    isPptFile(ext) ||
    isCadFile(ext) ||
    isEbookFile(ext) ||
    isDataFile(ext)
  );
}

// Check if file is ebook
export function isEbookFile(ext: string): boolean {
  const ebookExts = ["epub", "mobi", "azw", "azw3", "kf8", "ibooks", "fb2"];
  return ebookExts.includes(ext);
}

// Check if file is data / database
export function isDataFile(ext: string): boolean {
  const dataExts = [
    "db",
    "sqlite",
    "sqlite3",
    "mdb",
    "accdb",
    "jsonl",
    "ndjson",
    "parquet",
    "arrow",
  ];
  return dataExts.includes(ext);
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
    // Windows
    "wmv",
    "asf",
    "dvr-ms",
    // Apple/iOS
    "m4v",
    "3gp",
    "3g2",
    // Android
    "3gp",
    "3g2",
    "ogv",
    // Other
    "ts",
    "mts",
    "m2ts",
    "vob",
    "divx",
    "rm",
    "rmvb",
    "f4v",
    "h264",
    "hevc",
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
    // Apple/iOS
    "caf",
    "m4r",
    "m4p",
    "aif",
    // Android
    "amr",
    "mid",
    "midi",
    "imy",
    // Windows
    "wma",
    "wax",
    "asf",
    // Other
    "ape",
    "alac",
    "wv",
    "tak",
    "dsd",
    "dsf",
    "dff",
    "spx",
    "ra",
    "rm",
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
    // Windows
    "cab",
    "msi",
    // Apple/macOS/iOS
    "ipa",
    "pkg",
    "sit",
    "sitx",
    // Android
    "apk",
    "aab",
    // Linux
    "deb",
    "rpm",
    "snap",
    // Other
    "zst",
    "lz4",
    "lz",
    "tgz",
    "tbz2",
    "txz",
    "shar",
    "lzma",
    "arj",
    "ace",
  ];
  return archiveExts.includes(ext);
}

// Check if file is executable
export function isExecutableFile(ext: string): boolean {
  const execExts = [
    // Windows
    "exe",
    "dll",
    "msi",
    "bat",
    "cmd",
    "ps1",
    "vbs",
    "wsf",
    "cpl",
    "scr",
    // Linux
    "so",
    "deb",
    "rpm",
    // Apple/macOS/iOS
    "app",
    "dmg",
    "ipa",
    "kext",
    "dylib",
    "framework",
    // Android
    "apk",
    "dex",
    // Other
    "bin",
    "com",
    "run",
    "out",
  ];
  return execExts.includes(ext);
}

// Check if file is an image
export function isImageFile(ext: string): boolean {
  const imageExts = [
    "jpg",
    "jpeg",
    "png",
    "gif",
    "svg",
    "webp",
    "bmp",
    "ico",
    // Apple/iOS
    "heic",
    "heif",
    "tiff",
    "tif",
    // Android
    "webp",
    "avif",
    // Windows
    "wmf",
    "emf",
    "dib",
    // RAW formats (camera)
    "raw",
    "cr2",
    "cr3",
    "nef",
    "arw",
    "dng",
    "orf",
    "rw2",
    // Other
    "avif",
    "jxl",
    "tga",
    "pcx",
    "psd",
    "psb",
    "eps",
    "ico",
    "icns",
    "cur",
  ];
  return imageExts.includes(ext);
}

// Check if file is PDF
export function isPdfFile(ext: string): boolean {
  return ext === "pdf";
}

// Check if file is Word document
export function isWordFile(ext: string): boolean {
  const wordExts = ["doc", "docx", "dot", "dotx", "docm", "dotm"];
  return wordExts.includes(ext);
}

// Check if file is supported by the in-browser Word preview converter
export function isWordPreviewFile(ext: string): boolean {
  return ext === "doc" || ext === "docx";
}

// Check if file is a Word format that still has no browser-side preview path
export function isLegacyDocFile(ext: string): boolean {
  return isWordFile(ext) && !isWordPreviewFile(ext);
}

// Check if file is Excel spreadsheet
export function isExcelFile(ext: string): boolean {
  const excelExts = [
    "xls",
    "xlsx",
    "csv",
    "xlsm",
    "xlt",
    "xltx",
    "xlsb",
    "xlam",
    "ods",
  ];
  return excelExts.includes(ext);
}

// Check if file is PowerPoint presentation (any format)
export function isPptFile(ext: string): boolean {
  const pptExts = ["ppt", "pptx", "pot", "potx", "pps", "ppsx", "pptm", "odp"];
  return pptExts.includes(ext);
}

// Check if file is PowerPoint Open XML format (.pptx)
export function isPptxFile(ext: string): boolean {
  return ext === "pptx" || ext === "pptm";
}

// Check if file is legacy PowerPoint format (.ppt)
export function isLegacyPptFile(ext: string): boolean {
  return ext === "ppt";
}

// Check if file is HTML
export function isHtmlFile(ext: string): boolean {
  return ext === "html" || ext === "htm";
}

// Check if file is a CAD drawing
export function isCadFile(ext: string): boolean {
  return isDxfFile(ext) || isDwgFile(ext);
}

// Check if file is AutoCAD Drawing Exchange Format
export function isDxfFile(ext: string): boolean {
  return ext === "dxf";
}

// Check if file is AutoCAD native Drawing format
export function isDwgFile(ext: string): boolean {
  return ext === "dwg";
}

const FILE_LINK_EXTENSIONS = new Set([
  // Images
  "jpg",
  "jpeg",
  "png",
  "gif",
  "svg",
  "webp",
  "bmp",
  "ico",
  "heic",
  "heif",
  "avif",
  "tiff",
  "tif",
  "psd",
  "tga",
  "icns",
  // Documents
  "pdf",
  "doc",
  "docx",
  "xls",
  "xlsx",
  "csv",
  "ppt",
  "pptx",
  "odt",
  "ods",
  "odp",
  "rtf",
  "epub",
  "mobi",
  // Web
  "html",
  "htm",
  // Code / text
  "js",
  "ts",
  "jsx",
  "tsx",
  "py",
  "java",
  "cpp",
  "c",
  "h",
  "css",
  "scss",
  "json",
  "xml",
  "txt",
  "vue",
  "svelte",
  "go",
  "rs",
  "rb",
  "php",
  "swift",
  "kt",
  "dart",
  "lua",
  "r",
  "pl",
  "sql",
  "yaml",
  "yml",
  "toml",
  "ini",
  "cfg",
  "sh",
  "bash",
  "zsh",
  "fish",
  "ps1",
  "md",
  "markdown",
  "tex",
  "graphql",
  "proto",
  // Diagrams
  "excalidraw",
  "exdraw",
  // CAD
  "dxf",
  "dwg",
  // Media
  "mp4",
  "webm",
  "mov",
  "avi",
  "mkv",
  "flv",
  "wmv",
  "3gp",
  "3g2",
  "ts",
  "mts",
  "mp3",
  "wav",
  "ogg",
  "flac",
  "aac",
  "m4a",
  "wma",
  "opus",
  "aiff",
  "amr",
  "caf",
  // Archives
  "zip",
  "rar",
  "7z",
  "tar",
  "gz",
  "apk",
  "ipa",
  "dmg",
  // Fonts
  "ttf",
  "otf",
  "woff",
  "woff2",
  // Data
  "db",
  "sqlite",
  "sqlite3",
  "jsonl",
  "parquet",
]);

export interface FileLinkInfo {
  isFile: boolean;
  fileName: string;
}

function getFileLinkInfoFromName(candidate: string): FileLinkInfo {
  const fileName = candidate.trim().split(/[\\/]/).pop() || "";
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex < 1) return { isFile: false, fileName: "" };
  const ext = fileName.slice(dotIndex + 1).toLowerCase();
  if (FILE_LINK_EXTENSIONS.has(ext)) {
    return { isFile: true, fileName };
  }
  return { isFile: false, fileName: "" };
}

export function isFileLink(href: string): FileLinkInfo {
  try {
    const url = new URL(href, window.location.origin);
    const pathname = url.pathname;
    const lastSegment = pathname.split("/").pop() || "";
    const pathInfo = getFileLinkInfoFromName(decodeURIComponent(lastSegment));
    if (pathInfo.isFile) {
      return pathInfo;
    }

    for (const key of ["filename", "fileName", "name", "file", "path"]) {
      const value = url.searchParams.get(key);
      if (!value) continue;
      const queryInfo = getFileLinkInfoFromName(decodeURIComponent(value));
      if (queryInfo.isFile) {
        return queryInfo;
      }
    }

    const disposition = url.searchParams.get("response-content-disposition");
    if (disposition) {
      const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
      if (match?.[1]) {
        const dispositionInfo = getFileLinkInfoFromName(
          decodeURIComponent(match[1]),
        );
        if (dispositionInfo.isFile) {
          return dispositionInfo;
        }
      }
    }
  } catch {
    // invalid URL, ignore
  }
  return { isFile: false, fileName: "" };
}

export function getFileLinkInfo(
  href: string,
  displayName?: string,
): FileLinkInfo {
  const hrefInfo = isFileLink(href);
  if (hrefInfo.isFile) return hrefInfo;
  return displayName ? getFileLinkInfoFromName(displayName) : hrefInfo;
}

// Check if file type is supported for preview
export function isPreviewableFile(ext: string): boolean {
  return (
    isImageFile(ext) ||
    isPdfFile(ext) ||
    isWordFile(ext) ||
    isExcelFile(ext) ||
    isPptFile(ext) ||
    isCadFile(ext) ||
    isHtmlFile(ext) ||
    isCodeFile(ext) ||
    isMarkdownFile(ext) ||
    isExcalidrawFile(ext) ||
    isVideoFile(ext) ||
    isAudioFile(ext)
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
    // More web/frontend
    "html",
    "htm",
    "css",
    "scss",
    "sass",
    "less",
    "styl",
    "svelte",
    "astro",
    // More backend
    "cs",
    "vb",
    "swift",
    "kt",
    "kts",
    "scala",
    "dart",
    "lua",
    "r",
    "pl",
    "sql",
    "graphql",
    "gql",
    "proto",
    "thrift",
    // Config/data
    "env",
    "conf",
    "properties",
    "gradle",
    "cmake",
    "makefile",
    "dockerfile",
    // Shell
    "fish",
    "ps1",
    "bat",
    "cmd",
    // Other
    "tex",
    "log",
    "diff",
    "patch",
  ];
  return codeExts.includes(ext);
}

// Check if file is markdown
export function isMarkdownFile(fileName: string): boolean {
  const ext = getFileExtension(fileName);
  return ext === "md" || ext === "markdown";
}

/**
 * The preview toolbar's language chip only pays its way when it says more
 * than the extension already visible in the file name (md → "markdown" or
 * html → "html" would just repeat it).
 */
export function shouldShowLanguageBadge(
  codeFile: boolean,
  language: string,
  fileName: string,
): boolean {
  if (!codeFile || !language) return false;
  return language.toLowerCase() !== getFileExtension(fileName);
}

// Check if file is Excalidraw
export function isExcalidrawFile(ext: string): boolean {
  return ext === "excalidraw" || ext === "exdraw";
}
