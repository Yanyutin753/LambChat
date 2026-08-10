/** @vitest-environment jsdom */

import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import {
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $isTextNode,
  type LexicalEditor,
} from "lexical";
import { useEffect, useRef } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { SlashCommandPlugin } from "../SlashCommandPlugin";

const writerSkill = {
  name: "writer",
  description: "Write and edit text",
  tags: ["writing"],
};

function CaptureEditor({
  onReady,
}: {
  onReady: (editor: LexicalEditor) => void;
}) {
  const [editor] = useLexicalComposerContext();
  useEffect(() => {
    onReady(editor);
  }, [editor, onReady]);
  return null;
}

function PluginFixture({
  onReady,
}: {
  onReady: (editor: LexicalEditor) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  return (
    <LexicalComposer
      initialConfig={{
        namespace: "SlashCommandPluginTest",
        onError(error) {
          throw error;
        },
        editorState: () => {
          const paragraph = $createParagraphNode();
          const text = $createTextNode("/wri");
          paragraph.append(text);
          $getRoot().append(paragraph);
          text.select(4, 4);
        },
      }}
    >
      <div ref={containerRef}>
        <PlainTextPlugin
          contentEditable={<ContentEditable aria-label="message" />}
          placeholder={null}
          ErrorBoundary={LexicalErrorBoundary}
        />
      </div>
      <SlashCommandPlugin
        availableSkills={[writerSkill]}
        enabledSkillNames={[]}
        containerRef={containerRef}
      />
      <CaptureEditor onReady={onReady} />
    </LexicalComposer>
  );
}

function selectOffset(editor: LexicalEditor, offset: number) {
  act(() => {
    editor.update(
      () => {
        const node = $getRoot().getFirstDescendant();
        if (!$isTextNode(node)) throw new Error("Composer text node missing");
        node.select(offset, offset);
      },
      { discrete: true },
    );
  });
}

describe("SlashCommandPlugin dismissal state", () => {
  test.each(["outside press", "Escape"])(
    "%s suppresses only the unchanged active token",
    (dismissal) => {
      let editor: LexicalEditor | null = null;
      render(<PluginFixture onReady={(value) => (editor = value)} />);
      expect(editor).not.toBeNull();
      selectOffset(editor!, 4);
      expect(
        screen.getByRole("listbox", { name: "Slash commands" }),
      ).toBeVisible();

      const textbox = screen.getByRole("textbox", { name: "message" });
      if (dismissal === "Escape") {
        fireEvent.keyDown(textbox, { key: "Escape" });
      } else {
        fireEvent.mouseDown(textbox);
      }
      selectOffset(editor!, 2);
      expect(
        screen.queryByRole("listbox", { name: "Slash commands" }),
      ).not.toBeInTheDocument();

      selectOffset(editor!, 0);
      selectOffset(editor!, 4);
      expect(
        screen.getByRole("listbox", { name: "Slash commands" }),
      ).toBeVisible();
    },
  );
});
