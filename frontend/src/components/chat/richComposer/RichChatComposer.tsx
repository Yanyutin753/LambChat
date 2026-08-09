import {
  LexicalComposer,
  type InitialConfigType,
} from "@lexical/react/LexicalComposer";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import { forwardRef, useCallback, useRef } from "react";
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

export interface RichChatComposerChange {
  snapshot: ComposerSnapshot;
  projection: ComposerProjection;
}

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
}

export const RichChatComposer = forwardRef<
  RichChatComposerHandle,
  RichChatComposerProps
>(function RichChatComposer(
  { ariaLabel, placeholder, className, onChange, onError },
  ref,
) {
  const lastSnapshotRef = useRef<ComposerSnapshot | undefined>(undefined);
  const handleChange = useCallback(
    (change: RichChatComposerChange) => {
      lastSnapshotRef.current = change.snapshot;
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
      <div className={`rich-chat-composer${className ? ` ${className}` : ""}`}>
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
        />
      </div>
    </LexicalComposer>
  );
});
