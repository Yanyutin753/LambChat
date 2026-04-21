import { getFullUrl } from "../../../../services/api/config";
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

export interface FileManifestEntry {
  url: string;
  is_binary: boolean;
  size: number;
  content_type?: string;
}

interface ProjectRevealResultBase {
  type: "project_reveal";
  name: string;
  description?: string;
  template: ProjectTemplate;
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

export type ParsedProjectRevealData =
  | {
      version: 1;
      name: string;
      template: ProjectTemplate;
      entry?: string;
      path?: string;
      fileCount: number;
      files: Record<string, string>;
    }
  | {
      version: 2;
      name: string;
      template: ProjectTemplate;
      entry?: string;
      path?: string;
      fileCount: number;
      files: Record<string, FileManifestEntry>;
    };

export interface ParsedProjectRevealSummary {
  projectName: string;
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
      s3Key?: string;
      signedUrl?: string;
      fileSize?: number;
    }
  | {
      kind: "project";
      previewKey: string;
      project: ParsedProjectRevealData;
      openInFullscreen?: boolean;
    };

function isProjectRevealV2(
  result: ProjectRevealResultV1 | ProjectRevealResultV2,
): result is ProjectRevealResultV2 {
  if ("version" in result && result.version === 2) return true;
  const firstFile = Object.values(result.files)[0];
  return (
    typeof firstFile === "object" && firstFile !== null && "url" in firstFile
  );
}

export function parseProjectRevealSummary(input: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  parseErrorMessage: string;
}): ParsedProjectRevealSummary {
  const { args, result, parseErrorMessage } = input;
  let projectName = "";
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
              | ProjectRevealResultV2)
          : (result as unknown as
              | ProjectRevealResultV1
              | ProjectRevealResultV2);

      if (raw.error) {
        error = raw.message || raw.error;
      } else if (isProjectRevealV2(raw)) {
        projectName = raw.name || "";
        projectPath = raw.path || "";
        template = raw.template || "vanilla";
        fileCount = raw.file_count || Object.keys(raw.files).length;
        parsed = {
          version: 2,
          name: projectName,
          path: projectPath,
          template,
          entry: raw.entry,
          fileCount,
          files: raw.files,
        };
      } else {
        projectName = raw.name || "";
        projectPath = raw.path || "";
        template = raw.template || "vanilla";
        fileCount = raw.file_count || Object.keys(raw.files).length;
        parsed = {
          version: 1,
          name: projectName,
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
    template,
    error,
    fileCount,
    projectPath,
    parsed,
  };
}

export async function loadProjectRevealFiles(
  project: Extract<ParsedProjectRevealData, { version: 2 }>,
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

  const entries = await Promise.all(
    textEntries.map(async ([path, entry]): Promise<[string, string] | null> => {
      try {
        const fullUrl = getFullUrl(entry.url) || entry.url;
        const resp = await fetch(fullUrl);
        if (!resp.ok) {
          console.warn(
            `[reveal_project] Failed to fetch ${path}: ${resp.status}`,
          );
          return null;
        }
        const text = await resp.text();
        return [path, text];
      } catch (error) {
        console.warn(`[reveal_project] Error fetching ${path}:`, error);
        return null;
      }
    }),
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
  return loadedProjectRevealFilesCache.get(previewKey) || null;
}

export async function loadProjectRevealFilesCached(input: {
  previewKey: string;
  project: Extract<ParsedProjectRevealData, { version: 2 }>;
}): Promise<LoadedProjectRevealFiles> {
  const { previewKey, project } = input;
  const cached = loadedProjectRevealFilesCache.get(previewKey);
  if (cached) {
    return cached;
  }

  const inflight = inflightProjectRevealFilesCache.get(previewKey);
  if (inflight) {
    return inflight;
  }

  const request = loadProjectRevealFiles(project)
    .then((result) => {
      loadedProjectRevealFilesCache.set(previewKey, result);
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
