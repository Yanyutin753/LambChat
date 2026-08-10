/** @vitest-environment jsdom */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, test, vi } from "vitest";
import {
  RichChatComposer,
  type RichChatComposerChange,
  type RichChatComposerHandle,
} from "../RichChatComposer";

const writerSkill = {
  name: "writer",
  description: "Write and edit text",
  tags: ["writing"],
};

describe("rich composer slash Skill workflow", () => {
  test("opens only for an explicit command slash and inserts with Enter", () => {
    const handle = createRef<RichChatComposerHandle>();
    let latest: RichChatComposerChange | undefined;
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
        onChange={(change) => {
          latest = change;
        }}
      />,
    );

    act(() => handle.current?.insertText("请使用 /wri"));
    expect(
      screen.getByRole("listbox", { name: "Slash commands" }),
    ).toBeVisible();

    fireEvent.keyDown(screen.getByRole("textbox", { name: "message" }), {
      key: "Enter",
    });

    expect(
      screen.queryByRole("listbox", { name: "Slash commands" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
    expect(latest?.projection.message).toBe("请使用");
    expect(latest?.projection.enabledSkills).toEqual(["writer"]);
  });

  test("renders above the app in a portal and supports pointer selection", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
      />,
    );
    act(() => handle.current?.insertText("/wri"));

    const popup = screen.getByRole("listbox", { name: "Slash commands" });
    expect(popup.parentElement).toBe(document.body);

    fireEvent.mouseDown(screen.getByRole("option", { name: "writer" }));

    expect(popup).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
  });

  test.each(["https://example.com", "a/b", "/home/user"])(
    "does not open for %s",
    (text) => {
      const handle = createRef<RichChatComposerHandle>();
      render(
        <RichChatComposer
          ref={handle}
          ariaLabel="message"
          availableSkills={[writerSkill]}
        />,
      );

      act(() => handle.current?.insertText(text));

      expect(
        screen.queryByRole("listbox", { name: "Slash commands" }),
      ).not.toBeInTheDocument();
    },
  );

  test("Escape closes the popup without changing what the user wrote", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
      />,
    );
    act(() => handle.current?.insertText("/wri"));

    fireEvent.keyDown(screen.getByRole("textbox", { name: "message" }), {
      key: "Escape",
    });

    expect(
      screen.queryByRole("listbox", { name: "Slash commands" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "message" })).toHaveTextContent(
      "/wri",
    );
  });

  test("an editor press keeps the unchanged slash token dismissed", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
      />,
    );
    act(() => handle.current?.insertText("/wri"));
    const editor = screen.getByRole("textbox", { name: "message" });

    fireEvent.mouseDown(editor);

    expect(
      screen.queryByRole("listbox", { name: "Slash commands" }),
    ).not.toBeInTheDocument();
    expect(editor).toHaveTextContent("/wri");
  });

  test("editing a dismissed slash token allows matching to resume", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
      />,
    );
    act(() => handle.current?.insertText("/wri"));
    fireEvent.keyDown(screen.getByRole("textbox", { name: "message" }), {
      key: "Escape",
    });

    act(() => handle.current?.insertText("t"));

    expect(
      screen.getByRole("listbox", { name: "Slash commands" }),
    ).toBeVisible();
  });

  test("an outside action closes the menu and still receives its click", () => {
    const handle = createRef<RichChatComposerHandle>();
    const onClick = vi.fn();
    render(
      <>
        <RichChatComposer
          ref={handle}
          ariaLabel="message"
          availableSkills={[writerSkill]}
        />
        <button type="button" onClick={onClick}>
          Outside action
        </button>
      </>,
    );
    act(() => handle.current?.insertText("/wri"));
    const action = screen.getByRole("button", { name: "Outside action" });

    fireEvent.mouseDown(action);
    fireEvent.click(action);

    expect(
      screen.queryByRole("listbox", { name: "Slash commands" }),
    ).not.toBeInTheDocument();
    expect(onClick).toHaveBeenCalledOnce();
  });

  test("a second slash closes the popup", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
      />,
    );
    act(() => handle.current?.insertText("/wri"));
    expect(
      screen.getByRole("listbox", { name: "Slash commands" }),
    ).toBeVisible();

    act(() => handle.current?.insertText("/"));

    expect(
      screen.queryByRole("listbox", { name: "Slash commands" }),
    ).not.toBeInTheDocument();
  });

  test("composition Enter does not choose a Skill", () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        availableSkills={[writerSkill]}
      />,
    );
    act(() => handle.current?.insertText("/wri"));

    fireEvent.keyDown(screen.getByRole("textbox", { name: "message" }), {
      key: "Enter",
      isComposing: true,
      keyCode: 229,
    });

    expect(
      screen.getByRole("listbox", { name: "Slash commands" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Skill writer" }),
    ).not.toBeInTheDocument();
  });
});
