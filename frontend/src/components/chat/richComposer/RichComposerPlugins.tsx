import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { OnChangePlugin } from "@lexical/react/LexicalOnChangePlugin";
import {
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $getSelection,
  $insertNodes,
  $isRangeSelection,
  $nodesOfType,
  COMMAND_PRIORITY_EDITOR,
  type EditorState,
} from "lexical";
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
} from "react";
import { projectComposerSnapshot } from "./composerProjection";
import type {
  ComposerSnapshot,
  FileReferenceDescriptor,
  SkillReferenceDescriptor,
} from "./composerTypes";
import type {
  RichChatComposerChange,
  RichChatComposerHandle,
} from "./RichChatComposer";
import {
  $createFileReferenceNode,
  FileReferenceNode,
} from "./nodes/FileReferenceNode";
import {
  $createSkillReferenceNode,
  SkillReferenceNode,
} from "./nodes/SkillReferenceNode";
import {
  INSERT_FILE_REFERENCE_COMMAND,
  INSERT_SKILL_REFERENCE_COMMAND,
  REMOVE_FILE_REFERENCE_COMMAND,
  UPDATE_FILE_REFERENCE_COMMAND,
} from "./nodes/referenceCommands";

function toSnapshot(editorState: EditorState): ComposerSnapshot {
  return {
    version: 1,
    editorState:
      editorState.toJSON() as unknown as ComposerSnapshot["editorState"],
  };
}

function ensureRangeSelection() {
  let selection = $getSelection();
  if (!$isRangeSelection(selection)) {
    const root = $getRoot();
    if (root.getChildrenSize() === 0) {
      root.append($createParagraphNode());
    }
    selection = root.selectEnd();
  }
  return selection;
}

function replaceDocumentWithPlainText(text: string) {
  const root = $getRoot();
  root.clear();
  const lines = text.split("\n");
  for (const line of lines) {
    const paragraph = $createParagraphNode();
    if (line) paragraph.append($createTextNode(line));
    root.append(paragraph);
  }
  root.selectEnd();
}

interface RichComposerPluginsProps {
  onChange?: (change: RichChatComposerChange) => void;
  onError?: (error: Error) => void;
}

export const RichComposerPlugins = forwardRef<
  RichChatComposerHandle,
  RichComposerPluginsProps
>(function RichComposerPlugins({ onChange, onError }, ref) {
  const [editor] = useLexicalComposerContext();

  useLayoutEffect(() => {
    return editor.registerCommand(
      INSERT_FILE_REFERENCE_COMMAND,
      (descriptor) => {
        const existing = $nodesOfType(FileReferenceNode).find(
          (node) => node.getDescriptor().referenceId === descriptor.referenceId,
        );
        if (existing) {
          existing.updateDescriptor(descriptor);
          existing.selectNext();
          return true;
        }
        ensureRangeSelection();
        $insertNodes([$createFileReferenceNode(descriptor)]);
        return true;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  useLayoutEffect(() => {
    return editor.registerCommand(
      INSERT_SKILL_REFERENCE_COMMAND,
      (descriptor) => {
        const existing = $nodesOfType(SkillReferenceNode).find(
          (node) => node.getDescriptor().skillName === descriptor.skillName,
        );
        if (existing) {
          existing.selectNext();
          return true;
        }
        ensureRangeSelection();
        $insertNodes([$createSkillReferenceNode(descriptor)]);
        return true;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  useLayoutEffect(() => {
    return editor.registerCommand(
      REMOVE_FILE_REFERENCE_COMMAND,
      (referenceId) => {
        const node = $nodesOfType(FileReferenceNode).find(
          (candidate) => candidate.getDescriptor().referenceId === referenceId,
        );
        node?.remove();
        return node !== undefined;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  useLayoutEffect(() => {
    return editor.registerCommand(
      UPDATE_FILE_REFERENCE_COMMAND,
      (update) => {
        const node = $nodesOfType(FileReferenceNode).find(
          (candidate) =>
            candidate.getDescriptor().referenceId === update.referenceId,
        );
        node?.updateDescriptor(update);
        return node !== undefined;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  const emitChange = useCallback(
    (editorState: EditorState) => {
      try {
        const snapshot = toSnapshot(editorState);
        onChange?.({ snapshot, projection: projectComposerSnapshot(snapshot) });
      } catch (error) {
        onError?.(
          error instanceof Error
            ? error
            : new Error("Rich composer update failed"),
        );
      }
    },
    [onChange, onError],
  );

  useImperativeHandle(
    ref,
    () => ({
      focus(options) {
        editor.focus(() => {
          if (options?.atEnd) {
            editor.update(() => $getRoot().selectEnd());
          }
        });
      },
      setPlainText(text) {
        editor.update(() => replaceDocumentWithPlainText(text), {
          discrete: true,
        });
      },
      restoreSnapshot(snapshot) {
        if (snapshot.editorState.root) {
          try {
            editor.setEditorState(
              editor.parseEditorState(JSON.stringify(snapshot.editorState)),
            );
            return;
          } catch (error) {
            onError?.(
              error instanceof Error
                ? error
                : new Error("Rich composer restore failed"),
            );
          }
        }
        editor.update(
          () => replaceDocumentWithPlainText(snapshot.plainText ?? ""),
          { discrete: true },
        );
      },
      getSnapshot() {
        return toSnapshot(editor.getEditorState());
      },
      insertText(text) {
        editor.update(() => ensureRangeSelection().insertText(text), {
          discrete: true,
        });
      },
      insertSkill(skill: SkillReferenceDescriptor) {
        editor.update(
          () => editor.dispatchCommand(INSERT_SKILL_REFERENCE_COMMAND, skill),
          { discrete: true },
        );
      },
      insertFileReference(file: FileReferenceDescriptor) {
        editor.update(
          () => editor.dispatchCommand(INSERT_FILE_REFERENCE_COMMAND, file),
          { discrete: true },
        );
      },
      removeFileReference(referenceId) {
        editor.update(
          () =>
            editor.dispatchCommand(REMOVE_FILE_REFERENCE_COMMAND, referenceId),
          { discrete: true },
        );
      },
      updateFileReference(update) {
        editor.update(
          () => editor.dispatchCommand(UPDATE_FILE_REFERENCE_COMMAND, update),
          { discrete: true },
        );
      },
    }),
    [editor, onError],
  );

  return (
    <>
      <HistoryPlugin />
      <OnChangePlugin
        onChange={emitChange}
        ignoreSelectionChange
        ignoreHistoryMergeTagChange
      />
    </>
  );
});
