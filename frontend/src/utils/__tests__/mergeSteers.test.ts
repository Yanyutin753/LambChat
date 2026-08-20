import type { Message } from "../../types/message";
import type { SteerItem } from "../../hooks/useAgent/steerQueue";
import { mergeMessagesWithSteers } from "../mergeSteers";

function msg(partial: Partial<Message> & Pick<Message, "id" | "role">): Message {
  return { content: "", timestamp: new Date("2026-08-20T10:00:00Z"), ...partial } as Message;
}

describe("mergeMessagesWithSteers", () => {
  test("preserves steer identity and explicit delivery status", () => {
    const merged = mergeMessagesWithSteers([], [
      {
        id: "client-1",
        content: "相同内容",
        queued: false,
        status: "failed",
        timestamp: new Date(1),
      },
    ]);

    expect(merged[0].id).toBe("client-1");
    expect(merged[0].metadata).toMatchObject({
      steer: true,
      steerStatus: "failed",
    });
  });
  test("按时间戳把插话插进消息流（流式回复之后、新轮次之前）", () => {
    const messages: Message[] = [
      msg({ id: "u1", role: "user", content: "任务" }),
      msg({
        id: "a1",
        role: "assistant",
        timestamp: new Date("2026-08-20T10:00:05Z"),
      }),
    ];
    const steers: SteerItem[] = [
      {
        id: "steer-1",
        content: "中途插话",
        queued: true,
        timestamp: new Date("2026-08-20T10:00:30Z"),
      },
    ];

    const merged = mergeMessagesWithSteers(messages, steers);
    expect(merged.map((m) => m.id)).toEqual(["u1", "a1", "steer-1"]);
    expect(merged[2].role).toBe("user");
    expect(merged[2].metadata).toEqual({ steer: true, queued: true });
  });

  test("送达后的插话排在早于它的新助手轮次之前", () => {
    const messages: Message[] = [
      msg({ id: "u1", role: "user" }),
      msg({
        id: "a1#t1",
        role: "assistant",
        timestamp: new Date("2026-08-20T10:00:05Z"),
      }),
      msg({
        id: "a1",
        role: "assistant",
        timestamp: new Date("2026-08-20T10:01:00Z"),
      }),
    ];
    const steers: SteerItem[] = [
      {
        id: "steer-1",
        content: "插话",
        queued: false,
        timestamp: new Date("2026-08-20T10:00:30Z"),
      },
    ];

    const merged = mergeMessagesWithSteers(messages, steers);
    expect(merged.map((m) => m.id)).toEqual(["u1", "a1#t1", "steer-1", "a1"]);
  });

  test("无插话时返回原数组", () => {
    const messages: Message[] = [msg({ id: "u1", role: "user" })];
    expect(mergeMessagesWithSteers(messages, [])).toBe(messages);
  });

  test("无法插入当前运行时的插话保留为下一条消息", () => {
    const merged = mergeMessagesWithSteers([], [
      {
        id: "steer-failed",
        content: "继续扩写",
        queued: false,
        deferred: true,
        timestamp: new Date("2026-08-20T10:00:30Z"),
      },
    ]);

    expect(merged).toHaveLength(1);
    expect(merged[0].metadata).toEqual({
      steer: true,
      queued: false,
      deferred: true,
    });
  });
});
