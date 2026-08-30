import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { OnChangePlugin } from "@lexical/react/LexicalOnChangePlugin";
import {
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  type EditorState,
} from "lexical";
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
} from "react";
import { projectComposerSnapshot } from "./composerProjection";
import type {
  ComposerSnapshot,
  FileReferenceDescriptor,
  RunModeKey,
  RunModesOptions,
  SkillReferenceDescriptor,
} from "./composerTypes";
import type {
  RichChatComposerChange,
  RichChatComposerHandle,
} from "./RichChatComposer";
import type { AvailableComposerSkill } from "./RichChatComposer";
import type { LongTextPasteOptions } from "./RichChatComposer";
import type { FilePasteOptions } from "./RichChatComposer";
import type { ChatInputSlashCommand } from "../chatInputSlashCommands";
import { SlashCommandPlugin } from "./SlashCommandPlugin";
import { LongTextPastePlugin } from "./LongTextPastePlugin";
import {
  INSERT_FILE_REFERENCE_COMMAND,
  INSERT_SKILL_REFERENCE_COMMAND,
  REMOVE_FILE_REFERENCE_COMMAND,
  UPDATE_FILE_REFERENCE_COMMAND,
} from "./nodes/referenceCommands";
import { SkillReferencePlugin } from "./SkillReferencePlugin";
import { FileReferencePlugin } from "./FileReferencePlugin";
import { AtomicReferenceDeletionPlugin } from "./AtomicReferenceDeletionPlugin";
import { RunModeReferencePlugin } from "./RunModeReferencePlugin";
import { $reconcileRunModeChips } from "./nodes/RunModeReferenceNode";
import { ArrowKeyPlugin, type ComposerArrowDirection } from "./ArrowKeyPlugin";
import { FilePastePlugin } from "./FilePastePlugin";

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
  availableSkills?: readonly AvailableComposerSkill[];
  containerRef: React.RefObject<HTMLDivElement | null>;
  onApplySlashCommand?: (command: ChatInputSlashCommand) => void;
  enabledSkillNames?: readonly string[];
  filePaste?: FilePasteOptions;
  longTextPaste?: LongTextPasteOptions;
  onRetryFileReference?: (referenceId: string) => void;
  runModes?: RunModesOptions;
  onArrowKey?: (
    direction: ComposerArrowDirection,
    editor: HTMLElement,
  ) => boolean;
}

export const RichComposerPlugins = forwardRef<
  RichChatComposerHandle,
  RichComposerPluginsProps
>(function RichComposerPlugins(
  {
    onChange,
    onError,
    availableSkills = [],
    containerRef,
    onApplySlashCommand,
    enabledSkillNames = [],
    filePaste,
    longTextPaste,
    onRetryFileReference,
    runModes,
    onArrowKey,
  },
  ref,
) {
  const [editor] = useLexicalComposerContext();
  // Draft replacement (setPlainText/restoreSnapshot) destroys leading chips;
  // re-insert them from the latest modes kept in this ref.
  const runModesRef = useRef<RunModesOptions | undefined>(runModes);
  useLayoutEffect(() => {
    runModesRef.current = runModes;
  }, [runModes]);
  const reconcileRunModeChips = useCallback(() => {
    const modes = runModesRef.current;
    if (!modes) return;
    editor.update(
      () =>
        $reconcileRunModeChips({
          auto: modes.autoEnabled,
          goal: modes.goalEnabled,
        }),
      { discrete: true },
    );
  }, [editor]);
  const handleRunModeRemoved = useCallback((key: RunModeKey) => {
    runModesRef.current?.onToggle(key, false);
  }, []);

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
        editor.update(
          () => {
            replaceDocumentWithPlainText(text);
            const modes = runModesRef.current;
            if (modes) {
              $reconcileRunModeChips({
                auto: modes.autoEnabled,
                goal: modes.goalEnabled,
              });
            }
          },
          {
            discrete: true,
          },
        );
      },
      restoreSnapshot(snapshot) {
        if (snapshot.editorState.root) {
          try {
            editor.setEditorState(
              editor.parseEditorState(JSON.stringify(snapshot.editorState)),
            );
            reconcileRunModeChips();
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
          () => {
            replaceDocumentWithPlainText(snapshot.plainText ?? "");
            const modes = runModesRef.current;
            if (modes) {
              $reconcileRunModeChips({
                auto: modes.autoEnabled,
                goal: modes.goalEnabled,
              });
            }
          },
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
    [editor, onError, reconcileRunModeChips],
  );

  return (
    <>
      <HistoryPlugin />
      <OnChangePlugin
        onChange={emitChange}
        ignoreSelectionChange
        ignoreHistoryMergeTagChange
      />
      <SlashCommandPlugin
        availableSkills={availableSkills}
        enabledSkillNames={enabledSkillNames}
        containerRef={containerRef}
        onApplyCommand={onApplySlashCommand}
      />
      <SkillReferencePlugin />
      <FileReferencePlugin onRetry={onRetryFileReference} />
      <AtomicReferenceDeletionPlugin onRunModeRemoved={handleRunModeRemoved} />
      {runModes ? <RunModeReferencePlugin runModes={runModes} /> : null}
      <ArrowKeyPlugin onArrowKey={onArrowKey} />
      {filePaste ? <FilePastePlugin options={filePaste} /> : null}
      {longTextPaste ? <LongTextPastePlugin options={longTextPaste} /> : null}
    </>
  );
});
