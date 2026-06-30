import type { MessagePart, ToolPart } from "../../../types";
import { getFullUrl } from "../../../services/api/config";
import {
  parseProjectRevealSummary,
  type ParsedProjectRevealData,
  type RevealPreviewRequest,
} from "./items/revealPreviewData";
import { getFileRevealAutoOpenKey } from "./items/fileRevealAutoOpen";
import { getProjectRevealAutoOpenKey } from "./items/projectRevealAutoOpen";

export type RevealArtifact =
  | {
      kind: "file";
      id: string;
      name: string;
      path: string;
      description?: string;
      fileSize?: number;
      preview: Extract<RevealPreviewRequest, { kind: "file" }>;
    }
  | {
      kind: "project";
      id: string;
      name: string;
      mode: "project" | "folder";
      fileCount: number;
      template: string;
      preview: Extract<RevealPreviewRequest, { kind: "project" }>;
    };

export interface RevealArtifactTreeFile {
  kind: "file";
  artifact: RevealArtifact & { kind: "file" };
}

export interface RevealArtifactTreeDir {
  kind: "dir";
  name: string;
  path: string;
  fileCount: number;
  dirCount: number;
  children: (RevealArtifactTreeDir | RevealArtifactTreeFile)[];
}

export interface RevealArtifactStats {
  fileCount: number;
  projectCount: number;
  totalCount: number;
}

interface ParsedFileReveal {
  filePath: string;
  description?: string;
  s3Key?: string;
  s3Url?: string;
  fileSize?: number;
}

function collectArtifactPart(part: MessagePart): RevealArtifact | null {
  if (part.type !== "artifact" || part.success !== true) {
    return null;
  }

  if (part.artifact.kind === "file") {
    return part.artifact;
  }

  const project = part.artifact.preview.project as ParsedProjectRevealData;
  if (!project || typeof project !== "object") {
    return null;
  }

  return {
    ...part.artifact,
    preview: {
      ...part.artifact.preview,
      project,
    },
  };
}

function parseJsonishResult(
  result: string | Record<string, unknown> | undefined,
): Record<string, unknown> | null {
  if (!result) return null;
  if (typeof result === "object") return result;

  try {
    return JSON.parse(result) as Record<string, unknown>;
  } catch {
    const match = result.match(/content='(.+?)'(\s|$)/);
    if (!match) return null;
    try {
      return JSON.parse(match[1].replace(/\\'/g, "'")) as Record<
        string,
        unknown
      >;
    } catch {
      return null;
    }
  }
}

function parseFileRevealPart(part: ToolPart): ParsedFileReveal | null {
  const parsed = parseJsonishResult(part.result);
  if (!parsed) {
    const filePath = (part.args.path as string) || "";
    return filePath ? { filePath } : null;
  }

  if (typeof parsed.key === "string" && typeof parsed.url === "string") {
    const meta =
      parsed._meta && typeof parsed._meta === "object"
        ? (parsed._meta as Record<string, unknown>)
        : null;
    const filePath =
      (typeof meta?.path === "string" && meta.path) ||
      (typeof parsed.name === "string" ? parsed.name : "");
    if (!filePath) return null;

    return {
      filePath,
      description:
        typeof meta?.description === "string" ? meta.description : undefined,
      s3Key: parsed.key,
      s3Url: getFullUrl(parsed.url) || parsed.url,
      fileSize: typeof parsed.size === "number" ? parsed.size : undefined,
    };
  }

  if (parsed.type === "file_reveal" && typeof parsed.file === "object") {
    const file = parsed.file as Record<string, unknown>;
    const filePath = typeof file.path === "string" ? file.path : "";
    if (!filePath || typeof file.error === "string") return null;

    return {
      filePath,
      description:
        typeof file.description === "string" ? file.description : undefined,
      s3Key: typeof file.s3_key === "string" ? file.s3_key : undefined,
      s3Url:
        typeof file.s3_url === "string" ? getFullUrl(file.s3_url) : undefined,
      fileSize: typeof file.size === "number" ? file.size : undefined,
    };
  }

  return null;
}

function collectFromPart(part: MessagePart, artifacts: RevealArtifact[]): void {
  if (part.type === "subagent") {
    for (const child of part.parts || []) {
      collectFromPart(child, artifacts);
    }
    return;
  }

  const artifactPart = collectArtifactPart(part);
  if (artifactPart) {
    artifacts.push(artifactPart);
    return;
  }

  if (
    part.type !== "tool" ||
    part.success !== true ||
    part.isPending ||
    part.cancelled
  ) {
    return;
  }

  if (part.name === "reveal_file") {
    const file = parseFileRevealPart(part);
    if (!file) return;

    const previewKey = getFileRevealAutoOpenKey({
      s3Key: file.s3Key,
      s3Url: file.s3Url,
      filePath: file.filePath,
    });
    if (!previewKey) return;

    const name = file.filePath.split("/").pop() || file.filePath;
    artifacts.push({
      kind: "file",
      id: `file:${previewKey}`,
      name,
      path: file.filePath,
      description: file.description,
      fileSize: file.fileSize,
      preview: {
        kind: "file",
        previewKey,
        filePath: file.filePath,
        s3Key: file.s3Key,
        signedUrl: file.s3Url,
        fileSize: file.fileSize,
      },
    });
    return;
  }

  if (part.name === "reveal_project") {
    const summary = parseProjectRevealSummary({
      args: part.args,
      result: part.result,
      parseErrorMessage: "Unable to parse project reveal result",
    });
    if (!summary.parsed || summary.error) return;

    const previewKey = getProjectRevealAutoOpenKey({
      projectPath: summary.projectPath,
      projectName: summary.projectName,
    });
    if (!previewKey) return;

    artifacts.push({
      kind: "project",
      id: `project:${previewKey}`,
      name: summary.projectName || "Untitled project",
      mode: summary.mode,
      fileCount: summary.fileCount,
      template: summary.template,
      preview: {
        kind: "project",
        previewKey,
        project: summary.parsed,
      },
    });
  }
}

export function collectRevealArtifacts(
  parts?: MessagePart[],
): RevealArtifact[] {
  const artifacts: RevealArtifact[] = [];
  for (const part of parts || []) {
    collectFromPart(part, artifacts);
  }
  return dedupeRevealArtifacts(artifacts);
}

function normalizeArtifactPath(path: string): string {
  return path
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/+/g, "/")
    .replace(/^\/+|\/+$/g, "");
}

function getRevealArtifactDedupeKey(artifact: RevealArtifact): string {
  if (artifact.kind === "file") {
    const normalizedPath = normalizeArtifactPath(artifact.path);
    return normalizedPath ? `file:${normalizedPath}` : artifact.id;
  }

  return `project:${artifact.preview.previewKey}`;
}

function dedupeRevealArtifacts(artifacts: RevealArtifact[]): RevealArtifact[] {
  const deduped = new Map<string, RevealArtifact>();

  for (const artifact of artifacts) {
    deduped.set(getRevealArtifactDedupeKey(artifact), artifact);
  }

  return [...deduped.values()];
}

function updateTreeCounts(node: RevealArtifactTreeDir): {
  fileCount: number;
  dirCount: number;
} {
  let fileCount = 0;
  let dirCount = 0;

  for (const child of node.children) {
    if (child.kind === "file") {
      fileCount += 1;
      continue;
    }

    const childCounts = updateTreeCounts(child);
    fileCount += childCounts.fileCount;
    dirCount += 1 + childCounts.dirCount;
  }

  node.fileCount = fileCount;
  node.dirCount = dirCount;
  return { fileCount, dirCount };
}

function sortTree(node: RevealArtifactTreeDir): void {
  node.children.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "dir" ? -1 : 1;
    if (a.kind === "dir" && b.kind === "dir") {
      return a.name.localeCompare(b.name);
    }
    return (a as RevealArtifactTreeFile).artifact.name.localeCompare(
      (b as RevealArtifactTreeFile).artifact.name,
    );
  });

  for (const child of node.children) {
    if (child.kind === "dir") sortTree(child);
  }
}

export function buildRevealArtifactTree(
  files: (RevealArtifact & { kind: "file" })[],
): RevealArtifactTreeDir {
  const root: RevealArtifactTreeDir = {
    kind: "dir",
    name: "",
    path: "",
    fileCount: 0,
    dirCount: 0,
    children: [],
  };

  for (const file of files) {
    // For HTTP URLs, place the file directly at the root level
    // to avoid creating a deep tree from the URL path segments
    if (/^https?:\/\//i.test(file.path)) {
      root.children.push({ kind: "file", artifact: file });
      continue;
    }

    const parts = file.path.split("/").filter(Boolean);
    parts.pop();
    let current = root;
    const currentPath: string[] = [];

    for (const part of parts) {
      currentPath.push(part);
      let child = current.children.find(
        (candidate) => candidate.kind === "dir" && candidate.name === part,
      );

      if (child?.kind !== "dir") {
        child = {
          kind: "dir",
          name: part,
          path: currentPath.join("/"),
          fileCount: 0,
          dirCount: 0,
          children: [],
        };
        current.children.push(child);
      }

      current = child;
    }

    current.children.push({ kind: "file", artifact: file });
  }

  sortTree(root);
  updateTreeCounts(root);
  return root;
}

export function getRevealArtifactStats(
  artifacts: RevealArtifact[],
): RevealArtifactStats {
  const fileCount = artifacts.filter(
    (artifact) => artifact.kind === "file",
  ).length;
  const projectCount = artifacts.filter(
    (artifact) => artifact.kind === "project",
  ).length;
  return {
    fileCount,
    projectCount,
    totalCount: fileCount + projectCount,
  };
}
