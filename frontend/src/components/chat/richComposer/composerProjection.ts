import type {
  ComposerProjection,
  ComposerSnapshot,
  SerializedComposerNode,
} from "./composerTypes";

interface ProjectionAccumulator {
  referenceIds: string[];
  referenceIdSet: Set<string>;
  skillNames: string[];
  skillNameSet: Set<string>;
  hasRichNode: boolean;
}

function projectNode(
  node: SerializedComposerNode,
  accumulator: ProjectionAccumulator,
): string {
  if (node.type === "text") return node.text ?? "";
  if (node.type === "linebreak") return "\n";

  if (node.type === "file-reference") {
    accumulator.hasRichNode = true;
    if (node.referenceId && !accumulator.referenceIdSet.has(node.referenceId)) {
      accumulator.referenceIdSet.add(node.referenceId);
      accumulator.referenceIds.push(node.referenceId);
    }
    return node.fileName ? `[引用文件：${node.fileName}]` : "";
  }

  if (node.type === "skill-reference") {
    accumulator.hasRichNode = true;
    if (node.skillName && !accumulator.skillNameSet.has(node.skillName)) {
      accumulator.skillNameSet.add(node.skillName);
      accumulator.skillNames.push(node.skillName);
    }
    return "";
  }

  if (node.type === "run-mode-reference") {
    return "";
  }

  const children = node.children ?? [];
  const separator = node.type === "root" ? "\n" : "";
  return children
    .map((child) => projectNode(child, accumulator))
    .join(separator);
}

export function projectComposerSnapshot(
  snapshot: ComposerSnapshot,
): ComposerProjection {
  const accumulator: ProjectionAccumulator = {
    referenceIds: [],
    referenceIdSet: new Set(),
    skillNames: [],
    skillNameSet: new Set(),
    hasRichNode: false,
  };
  const root = snapshot.editorState.root;
  const message = root ? projectNode(root, accumulator).trim() : "";

  return {
    message,
    activeReferenceIds: accumulator.referenceIds,
    enabledSkills: accumulator.skillNames,
    isEmpty: message.length === 0 && !accumulator.hasRichNode,
  };
}
