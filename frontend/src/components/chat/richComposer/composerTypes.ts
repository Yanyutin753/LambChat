export type FileReferenceStatus = "uploading" | "ready" | "failed";

export interface FileReferenceDescriptor {
  referenceId: string;
  fileName: string;
  category: "document";
  status: FileReferenceStatus;
}

export interface SkillReferenceDescriptor {
  skillName: string;
  tags: string[];
}

export interface SerializedComposerNode {
  type: string;
  version?: number;
  text?: string;
  children?: SerializedComposerNode[];
  referenceId?: string;
  fileName?: string;
  category?: string;
  status?: FileReferenceStatus;
  skillName?: string;
  tags?: string[];
  [key: string]: unknown;
}

export interface ComposerSnapshot {
  version: 1;
  editorState: {
    root?: SerializedComposerNode;
    [key: string]: unknown;
  };
  plainText?: string;
}

export interface LegacyComposerSnapshot {
  version: 0;
  plainText: string;
}

export type DecodedComposerHistoryEntry =
  | ComposerSnapshot
  | LegacyComposerSnapshot;

export interface ComposerProjection {
  message: string;
  activeReferenceIds: string[];
  enabledSkills: string[];
  isEmpty: boolean;
}
