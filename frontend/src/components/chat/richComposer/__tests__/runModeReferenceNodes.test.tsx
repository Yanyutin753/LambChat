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

describe("rich composer run mode reference nodes", () => {
  test("renders inline skill-style chips at the start of the message", async () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: true,
          goalEnabled: true,
          onToggle: () => undefined,
        }}
      />,
    );

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );
    expect(screen.getByRole("button", { name: "Goal" })).toBeVisible();

    const children =
      handle.current!.getSnapshot().editorState.root?.children?.[0]?.children ??
      [];
    expect(children[0]).toMatchObject({
      type: "run-mode-reference",
      modeKey: "auto",
    });
    expect(children[2]).toMatchObject({
      type: "run-mode-reference",
      modeKey: "goal",
    });
  });

  test("turning a mode off removes its chip from the message", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const { rerender } = render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: true,
          goalEnabled: true,
          onToggle: () => undefined,
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );

    rerender(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: false,
          goalEnabled: true,
          onToggle: () => undefined,
        }}
      />,
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Auto" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Goal" })).toBeVisible();
  });

  test("Backspace removes the whole chip and toggles the mode off", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const onToggle = vi.fn();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{ autoEnabled: true, goalEnabled: false, onToggle }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );

    act(() => {
      fireEvent.keyDown(screen.getByRole("textbox", { name: "message" }), {
        key: "Backspace",
      });
    });

    await waitFor(() => expect(onToggle).toHaveBeenCalledWith("auto", false));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Auto" }),
      ).not.toBeInTheDocument(),
    );
  });

  test("clicking a chip toggles the mode off", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const onToggle = vi.fn();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{ autoEnabled: true, goalEnabled: true, onToggle }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Auto" }));
    fireEvent.click(screen.getByRole("button", { name: "Goal" }));

    await waitFor(() => expect(onToggle).toHaveBeenCalledWith("auto", false));
    expect(onToggle).toHaveBeenCalledWith("goal", false);
  });

  test("replacing the draft keeps chips while the mode stays on", async () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: true,
          goalEnabled: false,
          onToggle: () => undefined,
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );

    act(() => handle.current?.setPlainText("next draft"));

    await waitFor(() => {
      const firstChild =
        handle.current!.getSnapshot().editorState.root?.children?.[0]
          ?.children?.[0];
      expect(firstChild).toMatchObject({ type: "run-mode-reference" });
    });
    expect(projectComposerSnapshot(handle.current!.getSnapshot()).message).toBe(
      "next draft",
    );
  });

  test("chips contribute no text to the projection", async () => {
    const handle = createRef<RichChatComposerHandle>();
    render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: true,
          goalEnabled: true,
          onToggle: () => undefined,
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );

    const projection = projectComposerSnapshot(handle.current!.getSnapshot());
    expect(projection.message).toBe("");
    expect(projection.isEmpty).toBe(true);
  });

  test("restored snapshots reconcile chips against current modes", async () => {
    const handle = createRef<RichChatComposerHandle>();
    const { rerender } = render(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: true,
          goalEnabled: true,
          onToggle: () => undefined,
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Auto" })).toBeVisible(),
    );
    act(() => handle.current?.setPlainText("draft"));
    const snapshot = handle.current!.getSnapshot();

    rerender(
      <RichChatComposer
        ref={handle}
        ariaLabel="message"
        runModes={{
          autoEnabled: false,
          goalEnabled: true,
          onToggle: () => undefined,
        }}
      />,
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Auto" }),
      ).not.toBeInTheDocument(),
    );

    act(() => handle.current?.restoreSnapshot(snapshot));

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Auto" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Goal" })).toBeVisible();
    expect(projectComposerSnapshot(handle.current!.getSnapshot()).message).toBe(
      "draft",
    );
  });
});
