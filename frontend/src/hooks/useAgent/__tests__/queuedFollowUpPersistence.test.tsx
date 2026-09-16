/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { useSteerQueue } from "../steerQueue";
import type { MessageAttachment } from "../../../types";

vi.mock("../../../services/api", () => ({
  sessionApi: { cancelSteer: vi.fn(async () => ({})) },
}));

beforeEach(() => sessionStorage.clear());

function mount(sessionId: string | null) {
  return renderHook(() =>
    useSteerQueue({
      sessionIdRef: { current: sessionId },
      deferSteer: vi.fn(),
    }),
  );
}

test("refresh restores queued messages, stable IDs, timestamps and attachments in order", () => {
  const first = mount("session-a");
  const files: MessageAttachment[] = [
    {
      id: "f1",
      key: "f1",
      name: "report.pdf",
      type: "document",
      mimeType: "application/pdf",
      size: 10,
    },
  ];
  act(() => {
    first.result.current.queueFollowUp("first");
    first.result.current.queueFollowUp("", files);
  });
  const queued = first.result.current.steerMessages;
  first.unmount();
  const restored = mount("session-a");
  expect(restored.result.current.steerMessages).toEqual(queued);
  expect(restored.result.current.steerMessages).toHaveLength(2);
});

test.each(["cancelSteer", "clearSteer"] as const)(
  "%s removes the persisted message before refresh",
  (action) => {
    const first = mount("session-a");
    act(() => first.result.current.queueFollowUp("queued"));
    const item = first.result.current.steerMessages[0];
    act(() => first.result.current[action](item.content, item.id));
    first.unmount();
    expect(mount("session-a").result.current.steerMessages).toEqual([]);
  },
);

test("clearing the view preserves the queue and switching sessions keeps them isolated", () => {
  const first = mount("session-a");
  act(() => first.result.current.queueFollowUp("belongs to A"));
  act(() => first.result.current.clearSteerMessages());
  expect(first.result.current.steerMessages).toEqual([]);
  act(() => first.result.current.restoreSteerMessages("session-b"));
  expect(first.result.current.steerMessages).toEqual([]);
  act(() => first.result.current.restoreSteerMessages("session-a"));
  expect(
    first.result.current.steerMessages.map((item) => item.content),
  ).toEqual(["belongs to A"]);
});

test("server pending steers are rehydrated from the server without resurrecting them from storage", () => {
  const first = mount("session-a");
  act(() => first.result.current.queueFollowUp("local follow-up"));
  act(() =>
    first.result.current.hydrateSteers([
      {
        message_id: "server-steer",
        content: "server message",
        created_at: new Date().toISOString(),
      },
    ]),
  );
  first.unmount();
  expect(
    mount("session-a").result.current.steerMessages.map((item) => item.content),
  ).toEqual(["local follow-up"]);
});

test("messages queued during the first submit become persistent when the session is assigned", () => {
  const first = mount(null);
  act(() => first.result.current.queueFollowUp("during submit"));
  act(() => first.result.current.bindSteerSession("new-session"));
  first.unmount();
  expect(
    mount("new-session").result.current.steerMessages.map(
      (item) => item.content,
    ),
  ).toEqual(["during submit"]);
});
