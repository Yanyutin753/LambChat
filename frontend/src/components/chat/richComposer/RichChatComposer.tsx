import {
  LexicalComposer,
  type InitialConfigType,
} from "@lexical/react/LexicalComposer";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import { forwardRef, useCallback, useRef, useState } from "react";
import type { SkillResponse } from "../../../types";
import type { ChatInputSlashCommand } from "../chatInputSlashCommands";
import type {
  ComposerProjection,
  ComposerSnapshot,
  FileReferenceDescriptor,
  FileReferenceStatus,
  SkillReferenceDescriptor,
} from "./composerTypes";
import { FileReferenceNode } from "./nodes/FileReferenceNode";
import { SkillReferenceNode } from "./nodes/SkillReferenceNode";
import { RichComposerPlugins } from "./RichComposerPlugins";

export interface LongTextPastePayload {
  referenceId: string;
  file: File;
  originalText: string;
}

export interface LongTextPasteOptions {
  enabled: boolean;
  validateCount: (count: number) => boolean;
  onCreate: (payload: LongTextPastePayload) => void;
}

export interface RichChatComposerChange {
  snapshot: ComposerSnapshot;
  projection: ComposerProjection;
}

export type AvailableComposerSkill = Pick<
  SkillResponse,
  "name" | "description" | "tags"
>;

export interface RichChatComposerHandle {
  focus(options?: { atEnd?: boolean }): void;
  setPlainText(text: string): void;
  restoreSnapshot(snapshot: ComposerSnapshot): void;
  getSnapshot(): ComposerSnapshot;
  insertText(text: string): void;
  insertSkill(skill: SkillReferenceDescriptor): void;
  insertFileReference(file: FileReferenceDescriptor): void;
  removeFileReference(referenceId: string): void;
  updateFileReference(update: {
    referenceId: string;
    status: FileReferenceStatus;
    fileName?: string;
  }): void;
}

export interface RichChatComposerProps {
  ariaLabel: string;
  placeholder?: string;
  className?: string;
  onChange?: (change: RichChatComposerChange) => void;
  onError?: (error: Error) => void;
  availableSkills?: readonly AvailableComposerSkill[];
  onApplySlashCommand?: (command: ChatInputSlashCommand) => void;
  longTextPaste?: LongTextPasteOptions;
  onRetryFileReference?: (referenceId: string) => void;
}

export const RichChatComposer = forwardRef<
  RichChatComposerHandle,
  RichChatComposerProps
>(function RichChatComposer(
  {
    ariaLabel,
    placeholder,
    className,
    onChange,
    onError,
    availableSkills,
    onApplySlashCommand,
    longTextPaste,
    onRetryFileReference,
  },
  ref,
) {
  const lastSnapshotRef = useRef<ComposerSnapshot | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [enabledSkillNames, setEnabledSkillNames] = useState<string[]>([]);
  const handleChange = useCallback(
    (change: RichChatComposerChange) => {
      lastSnapshotRef.current = change.snapshot;
      setEnabledSkillNames(change.projection.enabledSkills);
      onChange?.(change);
    },
    [onChange],
  );

  const initialConfig: InitialConfigType = {
    namespace: "LambChatRichComposer",
    nodes: [FileReferenceNode, SkillReferenceNode],
    theme: {
      paragraph: "rich-chat-composer__paragraph",
    },
    onError(error: Error) {
      onError?.(error);
    },
  };

  return (
    <LexicalComposer initialConfig={initialConfig}>
      <div
        ref={containerRef}
        className={`rich-chat-composer${className ? ` ${className}` : ""}`}
      >
        <PlainTextPlugin
          contentEditable={
            <ContentEditable
              className="rich-chat-composer__editor"
              aria-label={ariaLabel}
              spellCheck
            />
          }
          placeholder={
            placeholder ? (
              <div className="rich-chat-composer__placeholder">
                {placeholder}
              </div>
            ) : null
          }
          ErrorBoundary={LexicalErrorBoundary}
        />
        <RichComposerPlugins
          ref={ref}
          onChange={handleChange}
          onError={onError}
          availableSkills={availableSkills}
          containerRef={containerRef}
          onApplySlashCommand={onApplySlashCommand}
          enabledSkillNames={enabledSkillNames}
          longTextPaste={longTextPaste}
          onRetryFileReference={onRetryFileReference}
        />
      </div>
    </LexicalComposer>
  );
});
