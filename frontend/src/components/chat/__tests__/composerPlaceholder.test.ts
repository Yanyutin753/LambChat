import { resolveComposerPlaceholder } from "../composerPlaceholder";

test("returns no-permission copy when sending is not allowed", () => {
  expect(
    resolveComposerPlaceholder({ canSend: false, mentionMode: "persona", isLoading: false }),
  ).toBe("chat.noPermission");
});

test("returns default placeholder when idle", () => {
  expect(
    resolveComposerPlaceholder({ canSend: true, mentionMode: "persona", isLoading: false }),
  ).toBe("chat.placeholder");
});

test("returns team placeholder while composing a team mention", () => {
  expect(
    resolveComposerPlaceholder({ canSend: true, mentionMode: "team", isLoading: true }),
  ).toBe("chat.teamPlaceholder");
});

test("returns running-queue placeholder while the agent is running", () => {
  expect(
    resolveComposerPlaceholder({ canSend: true, mentionMode: "persona", isLoading: true }),
  ).toBe("chat.runningPlaceholder");
});
