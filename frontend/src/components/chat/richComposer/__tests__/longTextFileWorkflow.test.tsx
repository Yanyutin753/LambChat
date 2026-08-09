/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, test, vi } from "vitest";
import { PASTE_TEXT_THRESHOLD } from "../../chatInputConstants";
import {
  RichChatComposer,
  type LongTextPastePayload,
  type RichChatComposerChange,
  type RichChatComposerHandle,
} from "../RichChatComposer";

function pasteText(element: HTMLElement, text: string) {
  fireEvent.paste(element, {
    clipboardData: {
      files: [],
      getData: (type: string) => (type === "text/plain" ? text : ""),
    },
  });
}

describe("long text file reference workflow", () => {
  test("keeps the existing draft and files only the pasted fragment", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const created: LongTextPastePayload[] = [];
    let latest: RichChatComposerChange | undefined;
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        longTextPaste={{
          enabled: true,
          validateCount: () => true,
          onCreate: (payload) => created.push(payload),
        }}
        onChange={(change) => {
          latest = change;
        }}
      />,
    );
    act(() => handle.current?.insertText("已有草稿 "));
    const pasted = "新".repeat(PASTE_TEXT_THRESHOLD + 1);

    pasteText(screen.getByRole("textbox", { name: "message" }), pasted);

    expect(created).toHaveLength(1);
    await expect(created[0].file.text()).resolves.toBe(pasted);
    expect(latest?.projection.message).toBe(
      `已有草稿 [引用文件：${created[0].file.name}]`,
    );
    expect(latest?.projection.activeReferenceIds).toEqual([
      created[0].referenceId,
    ]);
    expect(
      screen.getByRole("button", {
        name: `File ${created[0].file.name}, uploading`,
      }),
    ).toBeVisible();
  });

  test("restores a removed reference without creating another upload", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const onCreate = vi.fn();
    let latest: RichChatComposerChange | undefined;
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        longTextPaste={{ enabled: true, validateCount: () => true, onCreate }}
        onChange={(change) => {
          latest = change;
        }}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "message" });
    fireEvent.focus(editor);
    act(() => handle.current?.focus({ atEnd: true }));
    pasteText(editor, "x".repeat(PASTE_TEXT_THRESHOLD + 1));
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(latest?.projection.activeReferenceIds).toHaveLength(1),
    );
    const snapshot = handle.current!.getSnapshot();

    act(
      () =>
        handle.current?.removeFileReference(
          latest!.projection.activeReferenceIds[0],
        ),
    );
    await waitFor(() =>
      expect(latest?.projection.activeReferenceIds).toEqual([]),
    );

    act(() => handle.current?.restoreSnapshot(snapshot));
    await waitFor(() =>
      expect(latest?.projection.activeReferenceIds).toHaveLength(1),
    );
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  test("shows failure and allows external retry state updates", () => {
    const handle = createRef<RichChatComposerHandle>();
    let payload: LongTextPastePayload | undefined;
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        longTextPaste={{
          enabled: true,
          validateCount: () => true,
          onCreate: (created) => {
            payload = created;
          },
        }}
      />,
    );
    pasteText(
      screen.getByRole("textbox", { name: "message" }),
      "x".repeat(PASTE_TEXT_THRESHOLD + 1),
    );

    act(() => {
      handle.current?.updateFileReference({
        referenceId: payload!.referenceId,
        status: "failed",
      });
    });
    expect(
      screen.getByRole("button", {
        name: `File ${payload!.file.name}, failed`,
      }),
    ).toBeVisible();
  });

  test("expanded mode keeps oversized paste as editable text", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const onCreate = vi.fn();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        longTextPaste={{ enabled: false, validateCount: () => true, onCreate }}
      />,
    );
    const pasted = "x".repeat(PASTE_TEXT_THRESHOLD + 1);
    pasteText(screen.getByRole("textbox", { name: "message" }), pasted);

    expect(onCreate).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: "message" }),
      ).toHaveTextContent(pasted),
    );
  });

  test("does not intercept when the attachment limit rejects the paste", async () => {
    const onCreate = vi.fn();
    render(
      <RichChatComposer
        ariaLabel="message"
        longTextPaste={{ enabled: true, validateCount: () => false, onCreate }}
      />,
    );
    const pasted = "x".repeat(PASTE_TEXT_THRESHOLD + 1);
    pasteText(screen.getByRole("textbox", { name: "message" }), pasted);

    expect(onCreate).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: "message" }),
      ).toHaveTextContent(pasted),
    );
  });
});
