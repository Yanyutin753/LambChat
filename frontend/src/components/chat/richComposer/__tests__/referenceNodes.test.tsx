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
import {
  RichChatComposer,
  type RichChatComposerHandle,
} from "../RichChatComposer";
import { projectComposerSnapshot } from "../composerProjection";
import type { ComposerSnapshot } from "../composerTypes";

describe("rich composer reference nodes", () => {
  test.each([
    ["uploading", "File notes.txt, uploading"],
    ["ready", "File notes.txt, ready"],
    ["failed", "File notes.txt, failed"],
  ] as const)("renders the %s file state accessibly", (status, label) => {
    const handle = createRef<RichChatComposerHandle>();
    render(<RichChatComposer ref={handle} ariaLabel="message" />);

    act(() => {
      handle.current?.insertFileReference({
        referenceId: `ref-${status}`,
        fileName: "notes.txt",
        category: "document",
        status,
      });
    });

    expect(screen.getByRole("button", { name: label })).toBeVisible();
  });

  test("hides trailing controls after upload and removes atomically", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(<RichChatComposer ref={handle} ariaLabel="message" />);

    act(() => {
      handle.current?.insertFileReference({
        referenceId: "ref-1",
        fileName: "draft.txt",
        category: "document",
        status: "uploading",
      });
      handle.current?.updateFileReference({
        referenceId: "ref-1",
        fileName: "notes.txt",
        status: "ready",
      });
    });
    expect(
      screen.getByRole("button", { name: "File notes.txt, ready" }),
    ).toBeVisible();
    const fileNode = handle
      .current!.getSnapshot()
      .editorState.root?.children?.[0]?.children?.find(
        (node) => node.type === "file-reference",
      );
    expect(fileNode).toMatchObject({ referenceNumber: 1 });
    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
    expect(screen.getByText(/(?:Reference|引用) 1/)).toBeVisible();
    expect(
      document.querySelector(".composer-reference-chip__status"),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Remove notes.txt" }),
    ).not.toBeInTheDocument();

    act(() => handle.current?.removeFileReference("ref-1"));
    expect(
      screen.queryByRole("button", { name: /File notes\.txt/ }),
    ).not.toBeInTheDocument();
  });

  test("keeps the Skill icon instead of rendering a remove cross", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(<RichChatComposer ref={handle} ariaLabel="message" />);

    act(() => handle.current?.insertSkill({ skillName: "writer", tags: [] }));

    expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Remove writer" }),
    ).not.toBeInTheDocument();
    const paragraph =
      handle.current!.getSnapshot().editorState.root?.children?.[0];
    expect(paragraph?.children?.at(-1)).toMatchObject({
      type: "text",
      text: " ",
    });
  });

  test("Backspace removes the whole atomic reference", async () => {
    const handle = createRef<RichChatComposerHandle>();
    render(<RichChatComposer ref={handle} ariaLabel="message" />);
    act(() => {
      handle.current?.insertFileReference({
        referenceId: "ref-delete",
        fileName: "delete-me.txt",
        category: "document",
        status: "ready",
      });
    });

    act(() => {
      fireEvent.keyDown(screen.getByRole("textbox", { name: "message" }), {
        key: "Backspace",
      });
    });

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /File delete-me\.txt/ }),
      ).not.toBeInTheDocument(),
    );
  });

  test("exports readable plain text for reference nodes", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(<RichChatComposer ref={handle} ariaLabel="message" />);

    act(() => {
      handle.current?.setPlainText("查看 ");
      handle.current?.insertFileReference({
        referenceId: "ref-1",
        fileName: "notes.txt",
        category: "document",
        status: "ready",
      });
      handle.current?.insertSkill({ skillName: "writer", tags: [] });
    });

    expect(projectComposerSnapshot(handle.current!.getSnapshot()).message).toBe(
      "查看 [引用文件：notes.txt]",
    );
  });

  test("degrades an unknown reference version to readable text", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(<RichChatComposer ref={handle} ariaLabel="message" />);
    const snapshot: ComposerSnapshot = {
      version: 1,
      editorState: {
        root: {
          children: [
            {
              children: [
                {
                  type: "file-reference",
                  version: 2,
                  referenceId: "old-ref",
                  fileName: "legacy.txt",
                  category: "document",
                  status: "ready",
                },
              ],
              direction: null,
              format: "",
              indent: 0,
              textFormat: 0,
              textStyle: "",
              type: "paragraph",
              version: 1,
            },
          ],
          direction: null,
          format: "",
          indent: 0,
          type: "root",
          version: 1,
        },
      },
    };

    act(() => handle.current?.restoreSnapshot(snapshot));

    expect(screen.getByRole("textbox", { name: "message" })).toHaveTextContent(
      "[引用文件：legacy.txt]",
    );
    expect(
      screen.queryByRole("button", { name: /legacy\.txt/ }),
    ).not.toBeInTheDocument();
  });

  test("offers retry for a failed file reference", () => {
    const handle = createRef<RichChatComposerHandle>();
    const onRetry = vi.fn();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        onRetryFileReference={onRetry}
      />,
    );
    act(() => {
      handle.current?.insertFileReference({
        referenceId: "ref-failed",
        fileName: "notes.txt",
        category: "document",
        status: "failed",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "Retry upload" }));

    expect(onRetry).toHaveBeenCalledWith("ref-failed");
  });
});
