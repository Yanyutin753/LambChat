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

  test("holds promotion while the session still has an active run", async () => {
    // 重进/断连恢复时插话可能仍在原 run 的队列里等注入：
    // 会话还在运行就补发会造出同会话并发 run，历史交错不可读
    const calls: string[] = [];
    const result = await promoteSteerFollowUps([item("s1", "要多点中国的")], {
      sessionId: "session-1",
      cancelSteer: async () => {
        calls.push("cancel");
      },
      sendMessage: async () => {
        calls.push("send");
      },
      clearSteer: () => {
        calls.push("clear");
      },
      isSessionActive: async () => true,
    });

    expect(calls).toEqual([]);
    expect(result).toEqual({ promoted: 0, skippedActive: 1 });
  });

  test("defers items while a local submission is in flight instead of dropping them", async () => {
    // run 结束的瞬间用户又手动发了一条：sendMessage 的在途守卫会静默
    // 丢弃补发调用，若先清了本地项这条排队消息就丢了——必须原样
    // 留在队列里等下一轮重试
    const calls: string[] = [];
    const result = await promoteSteerFollowUps(
      [item("s1", "第一条"), item("s2", "第二条")],
      {
        sessionId: "session-1",
        isSending: () => true,
        clearSteer: (content) => {
          calls.push(`clear:${content}`);
        },
        cancelSteer: async () => {
          calls.push("cancel");
        },
        sendMessage: async (content) => {
          calls.push(`send:${content}`);
        },
      },
    );

    expect(calls).toEqual([]);
    expect(result).toEqual({ promoted: 0, skippedActive: 2 });
  });

  test("stops mid-drain when a local submission starts, keeping the rest queued", async () => {
    // 多条排队逐条补发途中用户手动发送：剩余条目不在本轮流里补发
    const calls: string[] = [];
    let inFlight = false;
    const result = await promoteSteerFollowUps(
      [item("s1", "第一条"), item("s2", "第二条"), item("s3", "第三条")],
      {
        sessionId: "session-1",
        isSending: () => inFlight,
        clearSteer: (content) => {
          calls.push(`clear:${content}`);
        },
        cancelSteer: async () => {},
        sendMessage: async (content) => {
          calls.push(`send:${content}`);
          inFlight = true;
        },
      },
    );

    expect(calls).toEqual(["clear:第一条", "send:第一条"]);
    expect(result).toEqual({ promoted: 1, skippedActive: 2 });
  });

  test("status probe failure is treated as active (never double-send blind)", async () => {
    const sent: string[] = [];
    const result = await promoteSteerFollowUps([item("s1", "插话")], {
      sessionId: "session-1",
      cancelSteer: async () => {},
      sendMessage: async (content) => {
        sent.push(content);
      },
      isSessionActive: async () => {
        throw new Error("probe failed");
      },
    });

    expect(sent).toEqual([]);
    expect(result.skippedActive).toBe(1);
  });

  test("promotes as before when the session is idle", async () => {
    const calls: string[] = [];
    const result = await promoteSteerFollowUps([item("s1", "插话")], {
      sessionId: "session-1",
      cancelSteer: async () => {
        calls.push("cancel");
      },
      sendMessage: async () => {
        calls.push("send");
      },
      isSessionActive: async () => false,
    });

    expect(calls).toEqual(["cancel", "send"]);
    expect(result).toEqual({ promoted: 1, skippedActive: 0 });
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
