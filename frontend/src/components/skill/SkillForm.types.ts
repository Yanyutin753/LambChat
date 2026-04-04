import type { SkillResponse, SkillCreate, BinaryFileInfo } from "../../types/skill";

export interface FileEntry {
  path: string;
  content: string;
}

export interface TreeNode {
  name: string;
  type: "file" | "folder";
  fileIndex?: number;
  children: TreeNode[];
}

export interface SkillFormProps {
  skill?: SkillResponse | null;
  onSave: (data: SkillCreate) => Promise<boolean>;
  onCancel: () => void;
  isLoading?: boolean;
  onFullscreenChange?: (fullscreen: boolean) => void;
}

export interface SkillFormActions {
  name: string;
  description: string;
  tagsInput: string;
  enabled: boolean;
  errors: Record<string, string>;
  isEditing: boolean;
  isLoading: boolean;
  files: FileEntry[];
  activeFileIndex: number;
  binaryFiles: Record<string, BinaryFileInfo>;
  loadingFilePath: string | null; // kept for backwards compat in form views
  setName: (v: string) => void;
  setDescription: (v: string) => void;
  setEnabled: (v: boolean) => void;
  setTagsInput: (v: string) => void;
  setActiveFileIndex: (i: number) => void;
  updateFilePath: (i: number, p: string) => void;
  updateFileContent: (i: number, c: string) => void;
  removeFile: (i: number) => void;
  addFile: () => void;
  removeTag: (tag: string) => void;
  loadFileContent: (index: number) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  toggleFullscreen: (fs: boolean) => void;
}

export const DEFAULT_CONTENT = `---
name: skill-name
description: Describe what this skill does
---

# Skill Name

## Overview
Describe what this skill does.

## When to Use
- When condition 1
- When condition 2

## Instructions
1. Step 1
2. Step 2
3. Step 3

## Examples
Example usage here.
`;
