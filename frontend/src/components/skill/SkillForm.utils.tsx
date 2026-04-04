import { FileText, FileCode, File, Image, Film, Music } from "lucide-react";
import type { FileEntry, TreeNode } from "./SkillForm.types";

export function getFileIcon(path: string) {
  const name = path.split("/").pop() || path;
  const ext = name.includes(".") ? name.split(".").pop() : "";
  switch (ext?.toLowerCase()) {
    case "md":
      return <FileText size={14} className="text-blue-400 shrink-0" />;
    case "ts":
    case "tsx":
      return <FileCode size={14} className="text-blue-500 shrink-0" />;
    case "js":
    case "jsx":
      return <FileCode size={14} className="text-yellow-500 shrink-0" />;
    case "py":
      return <FileCode size={14} className="text-green-500 shrink-0" />;
    case "json":
      return <FileCode size={14} className="text-yellow-400 shrink-0" />;
    case "yaml":
    case "yml":
      return <FileCode size={14} className="text-pink-400 shrink-0" />;
    // Images
    case "jpg":
    case "jpeg":
    case "png":
    case "gif":
    case "webp":
    case "bmp":
    case "ico":
    case "svg":
    case "tiff":
    case "tif":
      return <Image size={14} className="text-emerald-500 shrink-0" />;
    // Video
    case "mp4":
    case "webm":
    case "mov":
    case "avi":
    case "mkv":
      return <Film size={14} className="text-purple-500 shrink-0" />;
    // Audio
    case "mp3":
    case "wav":
    case "ogg":
    case "aac":
    case "flac":
    case "m4a":
      return <Music size={14} className="text-pink-500 shrink-0" />;
    default:
      return (
        <File
          size={14}
          className="text-stone-400 dark:text-stone-500 shrink-0"
        />
      );
  }
}

export function normalizeTags(input: string): string[] {
  return Array.from(
    new Set(
      input
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    ),
  );
}

function escapeYamlString(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function buildSkillFrontmatter(
  name: string,
  description: string,
  tags: string[],
): string {
  const tagLines =
    tags.length > 0
      ? ["tags:", ...tags.map((tag) => `  - "${escapeYamlString(tag)}"`)]
      : ["tags: []"];

  return [
    "---",
    `name: "${escapeYamlString(name)}"`,
    `description: "${escapeYamlString(description)}"`,
    ...tagLines,
    "---",
  ].join("\n");
}

export function syncSkillMarkdownMetadata(
  content: string,
  name: string,
  description: string,
  tags: string[],
): string {
  const normalizedContent = content.replace(/\r\n/g, "\n");
  const body = normalizedContent
    .replace(/^---\n[\s\S]*?\n---\n?/, "")
    .trimStart();
  const frontmatter = buildSkillFrontmatter(name, description, tags);

  return body ? `${frontmatter}\n\n${body}` : `${frontmatter}\n`;
}

export function buildFileTree(files: FileEntry[]): TreeNode[] {
  const root: TreeNode[] = [];
  for (let i = 0; i < files.length; i++) {
    const path = files[i].path || `untitled-${i}`;
    const parts = path.split("/");
    let current = root;
    for (let j = 0; j < parts.length; j++) {
      const part = parts[j];
      const isFile = j === parts.length - 1;
      let existing = current.find(
        (n) => n.name === part && n.type === (isFile ? "file" : "folder"),
      );
      if (!existing) {
        existing = {
          name: part,
          type: isFile ? "file" : "folder",
          children: [],
        };
        if (isFile) existing.fileIndex = i;
        current.push(existing);
      } else if (isFile && !existing.fileIndex && existing.fileIndex !== 0) {
        existing.fileIndex = i;
      }
      if (!isFile) {
        current = existing.children;
      }
    }
  }
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((n) => {
      if (n.type === "folder") sortNodes(n.children);
    });
  };
  sortNodes(root);
  return root;
}
