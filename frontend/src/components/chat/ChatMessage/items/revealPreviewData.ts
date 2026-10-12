import type { ReactNode } from "react";
import {
  buildUploadProxyUrl,
  getFullUrl,
} from "../../../../services/api/config";
import { fetchDocumentText } from "../../../documents/documentFetchCache";
import { rewriteProjectTextFiles } from "./projectRevealAssetUtils";

export type ProjectTemplate =
  | "react"
  | "vue"
  | "vanilla"
  | "static"
  | "angular"
  | "svelte"
  | "solid"
  | "nextjs";

export type ProjectRevealMode = "project" | "folder";

export interface FileManifestEntry {
  url: string;
  is_binary: boolean;
  size: number;
  content_type?: string;
}

/** v3 manifest 项：路径是值，绝不充当 dict key（事件落库的 key 消毒会把路径的 '.' 改成 '_'） */
export interface FileManifestItem extends FileManifestEntry {
  path: string;
}

interface ProjectRevealResultBase {
  type: "project_reveal";
  name: string;
  description?: string;
  template: ProjectTemplate;
  mode?: ProjectRevealMode;
  entry?: string;
  path?: string;
  file_count?: number;
  error?: string;
  message?: string;
}

export interface ProjectRevealResultV1 extends ProjectRevealResultBase {
  files: Record<string, string>;
}

export interface ProjectRevealResultV2 extends ProjectRevealResultBase {
  version: 2;
  files: Record<string, FileManifestEntry>;
}

export interface ProjectRevealResultV3 extends ProjectRevealResultBase {
  version: 3;
  files: FileManifestItem[];
}

/** 按 URL 拉取文件的 manifest 形态（v2 路径 key / v3 路径列表，内部统一为 record） */
export interface ManifestProjectRevealData {
  version: 2 | 3;
  name: string;
  mode: ProjectRevealMode;
  template: ProjectTemplate;
  entry?: string;
  path?: string;
  fileCount: number;
  files: Record<string, FileManifestEntry>;
}

export type ParsedProjectRevealData =
  | {
      version: 1;
      name: string;
      mode: ProjectRevealMode;
      template: ProjectTemplate;
      entry?: string;
      path?: string;
      fileCount: number;
      files: Record<string, string>;
    }
  | ManifestProjectRevealData;

export function isManifestProject(
  parsed: ParsedProjectRevealData | null | undefined,
): parsed is ManifestProjectRevealData {
  return !!parsed && parsed.version !== 1;
}

export interface ParsedProjectRevealSummary {
  projectName: string;
  mode: ProjectRevealMode;
  template: ProjectTemplate;
  error: string;
  fileCount: number;
  projectPath: string;
  parsed: ParsedProjectRevealData | null;
}

export type RevealPreviewRequest =
  | {
      kind: "file";
      previewKey: string;
      filePath: string;
      content?: string;
      s3Key?: string;
      signedUrl?: string;
      imageUrl?: string;
      fileSize?: number;
      footer?: ReactNode;
    }
  | {
      kind: "project";
      previewKey: string;
      project: ParsedProjectRevealData;
      openInFullscreen?: boolean;
      footer?: ReactNode;
    };

function isProjectRevealManifest(
  result: ProjectRevealResultV1 | ProjectRevealResultV2 | ProjectRevealResultV3,
): result is ProjectRevealResultV2 | ProjectRevealResultV3 {
  if ("version" in result && (result.version === 2 || result.version === 3)) {
    return true;
  }
  // 无版本号的早期 v2 载荷靠首项形态识别
  const firstFile = Object.values(result.files)[0];
  return (
    typeof firstFile === "object" && firstFile !== null && "url" in firstFile
  );
}

// 上传 key 的文件名段格式：{YYYYMMDD_HHMMSS}_{hash8}_{原始文件名}
const UPLOADED_FILENAME_PREFIX = /^\d{8}_\d{6}_[0-9a-f]{8}_/;

/**
 * 还原被事件 key 消毒改写的 v2 路径 key。
 *
 * dual_writer 落库前会把含 '.' 的 dict key 改成 '_'（Mongo $set 拒写点号），
 * 历史 v2 manifest 的路径 key 因此失真（/index.html → /index_html），而 entry
 * 是值幸免——两边脱节后 sandpack 直接崩掉。上传 URL 的文件名段保留原始点号，
 * basename 可据此无损还原；只有 URL 文件名恰好等于 key 的去点形态时才还原，
 * 防止把正常 key 改错。
 */
function restoreManifestPathKey(path: string, url: string): string | null {
  const separator = path.lastIndexOf("/");
  const keyBasename = path.slice(separator + 1);
  // key 里还有点号 = 未被消毒，或文件本就无扩展名（还原也无从下手）
  if (!keyBasename || keyBasename.includes(".")) {
    return null;
  }
  const urlBasename = url.slice(url.lastIndexOf("/") + 1);
  const original = urlBasename.replace(UPLOADED_FILENAME_PREFIX, "");
  if (!original.includes(".")) {
    return null;
  }
  if (original.replace(/\./g, "_") !== keyBasename) {
    return null;
  }
  return `${path.slice(0, separator + 1)}${original}`;
}

function restoreManifestFileKeys(
  files: Record<string, FileManifestEntry>,
): Record<string, FileManifestEntry> {
  const restored: Record<string, FileManifestEntry> = {};
  let changed = false;
  for (const [path, entry] of Object.entries(files)) {
    const original = restoreManifestPathKey(path, entry.url);
    restored[original ?? path] = entry;
    changed = changed || original !== null;
  }
  return changed ? restored : files;
}

function manifestFilesToRecord(
  files: FileManifestItem[] | Record<string, FileManifestEntry>,
): Record<string, FileManifestEntry> {
  if (Array.isArray(files)) {
    const record: Record<string, FileManifestEntry> = {};
    for (const item of files) {
      if (item && typeof item.path === "string" && item.path) {
        const { path, ...entry } = item;
        record[path] = { ...entry, is_binary: entry.is_binary ?? false };
      }
    }
    return record;
  }
  return restoreManifestFileKeys(files);
}

export function parseProjectRevealSummary(input: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  parseErrorMessage: string;
}): ParsedProjectRevealSummary {
  const { args, result, parseErrorMessage } = input;
  let projectName = "";
  let mode: ProjectRevealMode = "project";
  let template: ProjectTemplate = "vanilla";
  let error = "";
  let fileCount = 0;
  let projectPath = "";
  let parsed: ParsedProjectRevealData | null = null;

  if (result) {
    try {
      const raw =
        typeof result === "string"
          ? (JSON.parse(result) as
              | ProjectRevealResultV1
              | ProjectRevealResultV2
              | ProjectRevealResultV3)
          : (result as unknown as
              | ProjectRevealResultV1
              | ProjectRevealResultV2
              | ProjectRevealResultV3);

      if (raw.error) {
        error = raw.message || raw.error;
      } else if (isProjectRevealManifest(raw)) {
        projectName = raw.name || "";
        projectPath = raw.path || "";
        mode = raw.mode || "project";
        template = raw.template || "vanilla";
        const files = manifestFilesToRecord(raw.files);
        fileCount = raw.file_count || Object.keys(files).length;
        parsed = {
          version: Array.isArray(raw.files) || raw.version === 3 ? 3 : 2,
          name: projectName,
          mode,
          path: projectPath,
          template,
          entry: raw.entry,
          fileCount,
          files,
        };
      } else {
        projectName = raw.name || "";
        projectPath = raw.path || "";
        mode = raw.mode || "project";
        template = raw.template || "vanilla";
        fileCount = raw.file_count || Object.keys(raw.files).length;
        parsed = {
          version: 1,
          name: projectName,
          mode,
          path: projectPath,
          template,
          entry: raw.entry,
          fileCount,
          files: raw.files,
        };
      }
    } catch {
      error = parseErrorMessage;
    }
  } else {
    projectName = (args.name as string) || "";
  }

  return {
    projectName,
    mode,
    template,
    error,
    fileCount,
    projectPath,
    parsed,
  };
}

// 项目文件全量预取的并发上限：无上限的 Promise.all 会瞬间打满浏览器
// 连接池并触发大量同时解析，长项目会话打开时直接卡死页面
const PROJECT_REVEAL_FETCH_CONCURRENCY = 6;
// 已加载项目文件内容的内存缓存上限：每个项目可能持有数 MB 文本，
// 反复切换会话若无淘汰会持续累积（历史上从不清空）
const PROJECT_REVEAL_FILES_CACHE_MAX_ENTRIES = 4;

async function mapWithConcurrency<T, R>(
  items: readonly T[],
  limit: number,
  worker: (item: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const runners = Array.from(
    { length: Math.min(Math.max(1, limit), items.length) },
    async () => {
      while (nextIndex < items.length) {
        const index = nextIndex;
        nextIndex += 1;
        results[index] = await worker(items[index]);
      }
    },
  );
  await Promise.all(runners);
  return results;
}

export async function loadProjectRevealFiles(
  project: ManifestProjectRevealData,
): Promise<{
  files: Record<string, string>;
  binaryFiles: Record<string, string>;
  failed: string[];
}> {
  const textEntries: Array<[string, FileManifestEntry]> = [];
  const binaryFiles: Record<string, string> = {};

  for (const [path, entry] of Object.entries(project.files)) {
    if (entry.is_binary) {
      binaryFiles[path] = getFullUrl(entry.url) || entry.url;
    } else {
      textEntries.push([path, entry]);
    }
  }

  const entries = await mapWithConcurrency(
    textEntries,
    PROJECT_REVEAL_FETCH_CONCURRENCY,
    async ([path, entry]): Promise<[string, string] | null> => {
      try {
        const fullUrl = getFullUrl(entry.url) || entry.url;
        const readUrl = buildUploadProxyUrl(entry.url) || fullUrl;
        const text = await fetchDocumentText(readUrl);
        return [path, text];
      } catch (error) {
        console.warn(`[reveal_project] Error fetching ${path}:`, error);
        return null;
      }
    },
  );

  const rawFiles: Record<string, string> = {};
  const failed: string[] = [];
  for (const entry of entries) {
    if (entry) {
      rawFiles[entry[0]] = entry[1];
    }
  }

  for (const [path] of textEntries) {
    if (!(path in rawFiles)) {
      failed.push(path);
    }
  }

  return {
    files: rewriteProjectTextFiles(rawFiles, binaryFiles),
    binaryFiles,
    failed,
  };
}

export function shouldShowProjectRevealLoadingError(input: {
  files: Record<string, string>;
  binaryFiles: Record<string, string>;
  manifestFiles: Record<string, FileManifestEntry>;
}): boolean {
  return (
    Object.keys(input.files).length === 0 &&
    Object.keys(input.binaryFiles).length === 0 &&
    Object.keys(input.manifestFiles).length > 0
  );
}

type LoadedProjectRevealFiles = Awaited<
  ReturnType<typeof loadProjectRevealFiles>
>;

const loadedProjectRevealFilesCache = new Map<
  string,
  LoadedProjectRevealFiles
>();
const inflightProjectRevealFilesCache = new Map<
  string,
  Promise<LoadedProjectRevealFiles>
>();

export function getCachedProjectRevealFiles(
  previewKey: string | null | undefined,
): LoadedProjectRevealFiles | null {
  if (!previewKey) return null;
  const cached = loadedProjectRevealFilesCache.get(previewKey);
  if (!cached) return null;
  // Map 按插入序维护 LRU：命中后重新插入刷新新鲜度
  loadedProjectRevealFilesCache.delete(previewKey);
  loadedProjectRevealFilesCache.set(previewKey, cached);
  return cached;
}

function rememberProjectRevealFiles(
  previewKey: string,
  result: LoadedProjectRevealFiles,
): void {
  loadedProjectRevealFilesCache.set(previewKey, result);
  while (
    loadedProjectRevealFilesCache.size > PROJECT_REVEAL_FILES_CACHE_MAX_ENTRIES
  ) {
    const oldestKey = loadedProjectRevealFilesCache.keys().next().value;
    if (oldestKey === undefined) break;
    loadedProjectRevealFilesCache.delete(oldestKey);
  }
}

export async function loadProjectRevealFilesCached(input: {
  previewKey: string;
  project: ManifestProjectRevealData;
}): Promise<LoadedProjectRevealFiles> {
  const { previewKey, project } = input;
  const cached = getCachedProjectRevealFiles(previewKey);
  if (cached) {
    return cached;
  }

  const inflight = inflightProjectRevealFilesCache.get(previewKey);
  if (inflight) {
    return inflight;
  }

  const request = loadProjectRevealFiles(project)
    .then((result) => {
      rememberProjectRevealFiles(previewKey, result);
      inflightProjectRevealFilesCache.delete(previewKey);
      return result;
    })
    .catch((error) => {
      inflightProjectRevealFilesCache.delete(previewKey);
      throw error;
    });

  inflightProjectRevealFilesCache.set(previewKey, request);
  return request;
}

export function clearProjectRevealFilesCache(): void {
  loadedProjectRevealFilesCache.clear();
  inflightProjectRevealFilesCache.clear();
}
