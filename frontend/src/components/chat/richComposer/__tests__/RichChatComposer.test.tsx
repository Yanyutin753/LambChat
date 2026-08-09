/** @vitest-environment jsdom */

import { act, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, test, vi } from "vitest";
import {
  RichChatComposer,
  type RichChatComposerChange,
  type RichChatComposerHandle,
} from "../RichChatComposer";

describe("RichChatComposer", () => {
  test("keeps ordinary writing as plain text", async () => {
    const handle = createRef<RichChatComposerHandle>();
    let latest: RichChatComposerChange | undefined;

    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        placeholder="输入消息"
        onChange={(change) => {
          latest = change;
        }}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "message" });
    act(() => handle.current?.insertText("前文 **仍是 Markdown**"));

    expect(editor).toHaveTextContent("前文 **仍是 Markdown**");
    expect(latest?.projection.message).toBe("前文 **仍是 Markdown**");
    expect(latest?.projection.enabledSkills).toEqual([]);
  });

  test("inserts atomic Skill and file references into the document", async () => {
    const handle = createRef<RichChatComposerHandle>();
    let latest: RichChatComposerChange | undefined;

    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        onChange={(change) => {
          latest = change;
        }}
      />,
    );

    act(() => {
      handle.current?.insertText("请处理 ");
      handle.current?.insertFileReference({
        referenceId: "ref-1",
        fileName: "notes.txt",
        category: "document",
        status: "uploading",
      });
      handle.current?.insertSkill({ skillName: "writer", tags: ["writing"] });
    });

    expect(
      screen.getByRole("button", { name: "File notes.txt, uploading" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
    expect(latest?.projection).toMatchObject({
      message: "请处理 [引用文件：notes.txt]",
      activeReferenceIds: ["ref-1"],
      enabledSkills: ["writer"],
      isEmpty: false,
    });
  });

  test("round-trips a versioned editor snapshot", async () => {
    const first = createRef<RichChatComposerHandle>();
    const second = createRef<RichChatComposerHandle>();
    const onChange = vi.fn();

    const { rerender } = render(
      <RichChatComposer ref={first} ariaLabel="first" onChange={onChange} />,
    );
    act(() => {
      first.current?.insertText("草稿");
      first.current?.insertSkill({ skillName: "writer", tags: [] });
    });
    const snapshot = first.current?.getSnapshot();

    rerender(
      <RichChatComposer ref={second} ariaLabel="second" onChange={onChange} />,
    );
    act(() => second.current?.restoreSnapshot(snapshot!));

    expect(screen.getByRole("textbox", { name: "second" })).toHaveTextContent(
      "草稿",
    );
    expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
    expect(second.current?.getSnapshot()).toEqual(snapshot);
  });

  test("does not insert the same Skill twice", () => {
    const handle = createRef<RichChatComposerHandle>();
    let latest: RichChatComposerChange | undefined;
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        onChange={(change) => {
          latest = change;
        }}
      />,
    );

    act(() => {
      handle.current?.insertSkill({ skillName: "writer", tags: [] });
      handle.current?.insertSkill({ skillName: "writer", tags: [] });
    });

    expect(
      screen.getAllByRole("button", { name: "Skill writer" }),
    ).toHaveLength(1);
    expect(latest?.projection.enabledSkills).toEqual(["writer"]);
  });
});
