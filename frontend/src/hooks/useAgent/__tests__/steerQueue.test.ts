import { describe, expect, test } from "vitest";
import {
  promoteSteerFollowUps,
  removeSteerItem,
  selectSteersForFollowUp,
} from "../steerQueue";

describe("selectSteersForFollowUp", () => {
  test("selects only accepted pending items when the active run ends", () => {
    const selected = selectSteersForFollowUp([
      {
        id: "pending",
        content: "继续",
        queued: true,
        status: "pending",
        timestamp: new Date(1),
      },
      {
        id: "failed",
        content: "不要自动发送",
        queued: false,
        status: "failed",
        timestamp: new Date(2),
      },
      {
        id: "delivered",
        content: "已送达",
        queued: false,
        timestamp: new Date(3),
      },
    ]);

    expect(selected.map((item) => item.id)).toEqual(["pending"]);
  });
});

test("removes a queued steer by id without deleting another identical message", () => {
  const first = {
    id: "first",
    content: "重复内容",
    queued: true,
    timestamp: new Date(1),
  };
  const second = { ...first, id: "second", timestamp: new Date(2) };

  expect(removeSteerItem([first, second], "重复内容", "second")).toEqual({
    removed: second,
    remaining: [first],
  });
});

describe("promoteSteerFollowUps", () => {
  const item = (id: string, content: string) => ({
    id,
    content,
    queued: true,
    status: "pending" as const,
    timestamp: new Date(1),
  });

  test("cancels the backend queue item before resending it as a normal message", async () => {
    const calls: string[] = [];
    await promoteSteerFollowUps([item("s1", "你还能干啥")], {
      sessionId: "session-1",
      cancelSteer: async (sessionId, content, messageId) => {
        calls.push(`cancel:${sessionId}:${content}:${messageId}`);
      },
      sendMessage: async (content) => {
        calls.push(`send:${content}`);
      },
    });

    expect(calls).toEqual([
      "cancel:session-1:你还能干啥:s1",
      "send:你还能干啥",
    ]);
  });

  test("keeps FIFO order across multiple items and forwards attachments", async () => {
    const calls: string[] = [];
    const attachments = [{ id: "f1", name: "a.png" }] as never[];
    await promoteSteerFollowUps(
      [item("s1", "第一条"), { ...item("s2", "第二条"), attachments }],
      {
        sessionId: "session-1",
        cancelSteer: async (_s, _c, messageId) => {
          calls.push(`cancel:${messageId}`);
        },
        sendMessage: async (content, sentAttachments) => {
          calls.push(`send:${content}:${sentAttachments === attachments}`);
        },
      },
    );

    expect(calls).toEqual([
      "cancel:s1",
      "send:第一条:false",
      "cancel:s2",
      "send:第二条:true",
    ]);
  });

  test("still resends when the backend cancel request fails", async () => {
    const sent: string[] = [];
    await promoteSteerFollowUps([item("s1", "重要插话")], {
      sessionId: "session-1",
      cancelSteer: async () => {
        throw new Error("network down");
      },
      sendMessage: async (content) => {
        sent.push(content);
      },
    });

    expect(sent).toEqual(["重要插话"]);
  });

  test("skips items cancelled while promotion was pending", async () => {
    const sent: string[] = [];
    await promoteSteerFollowUps([item("s1", "已取消"), item("s2", "保留")], {
      sessionId: "session-1",
      cancelSteer: async () => {},
      sendMessage: async (content) => {
        sent.push(content);
      },
      isCancelled: (id) => id === "s1",
    });

    expect(sent).toEqual(["保留"]);
  });

  test("clears local state first so the promotion effect does not retrigger", async () => {
    const cleared: Array<[string, string]> = [];
    const calls: string[] = [];
    await promoteSteerFollowUps([item("s1", "插话")], {
      sessionId: "session-1",
      clearSteer: (content, messageId) => {
        cleared.push([content, messageId]);
      },
      cancelSteer: async () => {
        calls.push("cancel");
      },
      sendMessage: async () => {
        calls.push("send");
      },
    });

    expect(cleared).toEqual([["插话", "s1"]]);
    expect(calls).toEqual(["cancel", "send"]);
  });

  test("does nothing without a session id", async () => {
    const calls: string[] = [];
    await promoteSteerFollowUps([item("s1", "插话")], {
      sessionId: null,
      cancelSteer: async () => {
        calls.push("cancel");
      },
      sendMessage: async () => {
        calls.push("send");
      },
    });

    expect(calls).toEqual([]);
  });
});
