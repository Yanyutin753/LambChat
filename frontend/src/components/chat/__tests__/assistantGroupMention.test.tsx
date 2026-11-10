/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useChatInputMentions } from "../useChatInputMentions";
const { members, search, teams } = vi.hoisted(() => ({
  members: [{ id: "b", name: "Bob", status: "active" }],
  search: vi.fn(() => ({ presets: [] })),
  teams: vi.fn(() => ({ teams: [] })),
}));
vi.mock("../../assistants/AssistantGroupContext", () => ({
  useAssistantGroupMembers: () => members,
}));
vi.mock("../../../hooks/useMentionSearch", () => ({
  useMentionSearch: search,
}));
vi.mock("../../../hooks/useTeamMentionSearch", () => ({
  useTeamMentionSearch: teams,
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
test("group picker inserts a readable mention and never searches private persona or team catalogues", () => {
  const write = vi.fn();
  const focus = vi.fn();
  const { result } = renderHook(() =>
    useChatInputMentions({
      input: "@Bo",
      cursorPosition: 3,
      mentionMode: "team",
      setComposerPlainText: write,
      setCursorPosition: vi.fn(),
      focusComposerAtEnd: focus,
    }),
  );
  expect(result.current.groupMatches).toEqual(members);
  expect(search).toHaveBeenLastCalledWith("Bo", false);
  expect(teams).toHaveBeenLastCalledWith("Bo", false);
  act(() => result.current.applyGroupMention(members[0]));
  expect(write).toHaveBeenCalledWith("@Bob ");
  expect(focus).toHaveBeenCalled();
});

test("selecting a member closes the picker even when composer projection trims the trailing space", () => {
  const write = vi.fn();
  const { result, rerender } = renderHook(
    ({ input }) =>
      useChatInputMentions({
        input,
        cursorPosition: input.length,
        mentionMode: "team",
        setComposerPlainText: write,
        setCursorPosition: vi.fn(),
        focusComposerAtEnd: vi.fn(),
      }),
    { initialProps: { input: "@Bo" } },
  );
  act(() => result.current.applyGroupMention(members[0]));
  rerender({ input: "@Bob" });
  expect(result.current.mention.isActive).toBe(false);
  rerender({ input: "@B" });
  expect(result.current.mention.isActive).toBe(true);
});
