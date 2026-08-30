export type FileReferenceStatus = "uploading" | "ready" | "failed";

export type RunModeKey = "auto" | "goal";

export interface RunModesOptions {
  autoEnabled: boolean;
  goalEnabled: boolean;
  onToggle: (key: RunModeKey, enabled: boolean) => void;
}

export interface FileReferenceDescriptor {
  referenceId: string;
  fileName: string;
  referenceNumber?: number;
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
  referenceNumber?: number;
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
  runModes: RunModeKey[];
  isEmpty: boolean;
}
