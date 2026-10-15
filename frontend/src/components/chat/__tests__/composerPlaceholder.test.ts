import { resolveComposerPlaceholder } from "../composerPlaceholder";

const idle = { canSend: true, mentionMode: "persona" as const, isLoading: false };

test.each([
  [{}, "chat.placeholder"],
  [{ sandbox: "cloud" }, "chat.cloudPlaceholder"],
  [{ sandbox: "local" }, "chat.localPlaceholder"],
  [{ sandbox: "unknown" }, "chat.placeholder"],
  [{ mentionMode: "team" as const, sandbox: "local" }, "chat.teamPlaceholder"],
  [{ isLoading: true, mentionMode: "team" as const }, "chat.runningPlaceholder"],
  [{ isLoading: true, sandbox: "local" }, "chat.runningPlaceholder"],
  [{ sendBlocked: true, isLoading: true }, "chat.replyRequiredPlaceholder"],
  [{ canSend: false, sendBlocked: true, isLoading: true }, "chat.noPermission"],
])("selects actionable copy for %j", (state, expected) => {
  expect(resolveComposerPlaceholder({ ...idle, ...state })).toBe(expected);
});
