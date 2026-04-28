/**
 * File utilities - main entry point
 * Re-exports all file utility functions for backward compatibility
 */

// File type checks
export {
  getFileExtension,
  isBinaryFile,
  isVideoFile,
  isAudioFile,
  isArchiveFile,
  isExecutableFile,
  isImageFile,
  isPdfFile,
  isWordFile,
  isExcelFile,
  isPptFile,
  isPptxFile,
  isLegacyPptFile,
  isLegacyDocFile,
  isHtmlFile,
  isPreviewableFile,
  isCodeFile,
  isMarkdownFile,
  isExcalidrawFile,
  isFileLink,
} from "./fileTypeChecks";
export type { FileLinkInfo } from "./fileTypeChecks";

// File type map and types
export {
  FILE_TYPE_MAP,
  MIME_TO_EXT,
  DEFAULT_FILE_TYPE,
  defaultStyles,
} from "./fileTypeMap";
export type { FileTypeInfo, Type } from "./fileTypeMap";

// File type info functions
export {
  getFileTypeInfo,
  getFileTypeInfoFromMime,
  getFileTypeInfoFromName,
} from "./fileTypeInfo";

// Language detection
export {
  getFileIconType,
  getFileTypeColor,
  detectLanguage,
} from "./detectLanguage";

// File size formatting
export { formatFileSize } from "./fileSize";
