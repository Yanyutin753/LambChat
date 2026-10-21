/** @vitest-environment jsdom */

import { act, fireEvent, render, screen } from "@testing-library/react";
import {
  $getRoot,
  $isTextNode,
  getNearestEditorFromDOMNode,
  UNDO_COMMAND,
} from "lexical";
import { createPortal } from "react-dom";
import { expect, test } from "vitest";
import "../../../../i18n";
import { useExpandedComposerHost } from "../../chatInputExpandedHost";
import { RichChatComposer } from "../RichChatComposer";

const original =
  "看完我发的内容，经常跟我倒苦水：看招聘软件上的数据合规岗，动辄要求有出海业务。";
const selected = "经常跟我倒苦水";
const expected =
  "看完我发的内容，跟：看招聘软件上的数据合规岗，动辄要求有出海业务。";
const from = original.indexOf(selected);

function Composer({ expanded }: { expanded: boolean }) {
  const { host, slotRef } = useExpandedComposerHost(expanded, () => {});
  return (
    <>
      <div ref={slotRef} />
      {host &&
        createPortal(
          <RichChatComposer ariaLabel="message" initialPlainText={original} />,
          host,
        )}
    </>
  );
}

function select(root: HTMLElement, start: number, end: number) {
  const editor = getNearestEditorFromDOMNode(root)!;
  act(() => {
    root.focus();
    editor.update(
      () => {
        const node = $getRoot().getFirstDescendant();
        if (!$isTextNode(node)) throw new Error("Expected a text node");
        node.select(start, end);
      },
      { discrete: true },
    );
  });
  return editor;
}

// The native IME captures the original replacement offsets before compositionstart.
async function replaceWithPinyin(
  root: HTMLElement,
  start: number,
  count: number,
) {
  await act(async () => {
    fireEvent.keyDown(root, { key: "Process", keyCode: 229 });
    fireEvent.compositionStart(root, { data: "" });
  });

  let previousLength = count;
  for (const text of ["g", "ge", "gen", "跟"]) {
    await act(async () => {
      fireEvent.compositionUpdate(root, { data: text });
      const node = root.querySelector("[data-lexical-text]")!
        .firstChild as Text;
      node.replaceData(start, previousLength, text);
      window
        .getSelection()!
        .setBaseAndExtent(node, start + text.length, node, start + text.length);
      fireEvent.input(root, {
        inputType: "insertCompositionText",
        data: text,
        isComposing: true,
      });
    });
    previousLength = text.length;
  }
  await act(async () => {
    fireEvent.compositionEnd(root, { data: "跟" });
  });
}

for (const expanded of [false, true]) {
  const mode = expanded ? "expanded" : "inline";

  test.each([false, true])(
    `${mode}: pinyin replacement preserves unselected text (backward=%s)`,
    async (backward) => {
      render(<Composer expanded={expanded} />);
      const root = screen.getByRole("textbox", { name: "message" });
      const end = from + selected.length;
      const editor = select(root, backward ? end : from, backward ? from : end);

      await replaceWithPinyin(root, from, selected.length);

      expect(root.textContent).toBe(expected);
      expect(
        editor.getEditorState().read(() => $getRoot().getTextContent()),
      ).toBe(expected);
      expect(editor.isComposing()).toBe(false);
    },
  );

  test.each(["Backspace", "Delete"])(
    `${mode}: %s before pinyin preserves unselected text`,
    async (key) => {
      render(<Composer expanded={expanded} />);
      const root = screen.getByRole("textbox", { name: "message" });
      const editor = select(root, from, from + selected.length);
      await act(async () => {
        fireEvent.keyDown(root, { key });
      });

      expect(root.textContent).toBe(
        "看完我发的内容，：看招聘软件上的数据合规岗，动辄要求有出海业务。",
      );
      await replaceWithPinyin(root, from, 0);

      expect(root.textContent).toBe(expected);
      expect(
        editor.getEditorState().read(() => $getRoot().getTextContent()),
      ).toBe(expected);
    },
  );

  test(`${mode}: typing pinyin at a caret keeps surrounding text`, async () => {
    render(<Composer expanded={expanded} />);
    const root = screen.getByRole("textbox", { name: "message" });
    select(root, from, from);

    await replaceWithPinyin(root, from, 0);

    expect(root.textContent).toBe(
      "看完我发的内容，跟经常跟我倒苦水：看招聘软件上的数据合规岗，动辄要求有出海业务。",
    );
  });

  test(`${mode}: cancelling before native insertion preserves the selected text`, async () => {
    render(<Composer expanded={expanded} />);
    const root = screen.getByRole("textbox", { name: "message" });
    const editor = select(root, from, from + selected.length);
    await act(async () => {
      fireEvent.compositionStart(root, { data: "" });
    });
    await act(async () => {
      fireEvent.compositionEnd(root, { data: "" });
    });

    expect(root.textContent).toBe(original);
    expect(editor.isComposing()).toBe(false);
  });

  test(`${mode}: undo restores the text replaced by pinyin`, async () => {
    render(<Composer expanded={expanded} />);
    const root = screen.getByRole("textbox", { name: "message" });
    const editor = select(root, from, from + selected.length);

    await replaceWithPinyin(root, from, selected.length);
    await act(async () => {
      editor.dispatchCommand(UNDO_COMMAND, undefined);
    });

    expect(root.textContent).toBe(original);
  });
}
