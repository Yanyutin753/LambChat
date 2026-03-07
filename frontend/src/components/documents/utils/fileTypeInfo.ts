/**
 * File type information utilities
 * Functions to get file type info from file names or MIME types
 */

import { getFileExtension } from "./fileTypeChecks";
import {
  FILE_TYPE_MAP,
  MIME_TO_EXT,
  DEFAULT_FILE_TYPE,
  type FileTypeInfo,
} from "./fileTypeMap";

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

// Re-export FileTypeInfo
export type { FileTypeInfo };
