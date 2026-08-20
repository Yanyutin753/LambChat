import type { Message } from "../../../types/message";
import { splitAssistantTurnOnSteerDelivery } from "../steerTurnSplit";

function msg(partial: Partial<Message> & Pick<Message, "id" | "role">): Message {
  return { content: "", timestamp: new Date(), ...partial } as Message;
}

describe("splitAssistantTurnOnSteerDelivery", () => {
  const base: Message[] = [
    msg({ id: "run1:user", role: "user", content: "开始任务" }),
    msg({
      id: "run1:assistant",
      role: "assistant",
      content: "第一轮回复",
      isStreaming: true,
      parts: [],
    }),
    msg({
      id: "steer-1",
      role: "user",
      content: "中途插话",
      metadata: { steered: true, queued: true },
    }),
  ];

  test("送达时封存旧助手轮次，插话后开新轮次接收后续事件", () => {
    const result = splitAssistantTurnOnSteerDelivery(base, "中途插话", "run1:assistant");

    expect(result.map((m) => m.id)).toEqual([
      "run1:user",
      "run1:assistant#t1",
      "steer-1",
      "run1:assistant",
    ]);
    const oldTurn = result[1];
    expect(oldTurn.isStreaming).toBe(false);
    const newTurn = result[3];
    expect(newTurn.role).toBe("assistant");
    expect(newTurn.isStreaming).toBe(true);
    expect(newTurn.parts).toEqual([]);
  });

  test("非插话的 user:message 不触发分割", () => {
    const noSteer: Message[] = [
      msg({ id: "run1:user", role: "user", content: "开始任务" }),
      msg({ id: "run1:assistant", role: "assistant", isStreaming: true }),
    ];
    expect(splitAssistantTurnOnSteerDelivery(noSteer, "普通消息", "run1:assistant")).toBe(
      noSteer,
    );
  });

  test("无匹配排队插话（内容不同）不分割", () => {
    expect(splitAssistantTurnOnSteerDelivery(base, "别的内容", "run1:assistant")).toBe(base);
  });

  test("多次送达递增轮次后缀", () => {
    const once = splitAssistantTurnOnSteerDelivery(base, "中途插话", "run1:assistant");
    const withSecondSteer = [
      ...once.slice(0, 3),
      msg({
        id: "run1:assistant",
        role: "assistant",
        isStreaming: true,
        parts: [],
      }),
      msg({
        id: "steer-2",
        role: "user",
        content: "第二次插话",
        metadata: { steered: true, queued: true },
      }),
    ];
    const twice = splitAssistantTurnOnSteerDelivery(
      withSecondSteer,
      "第二次插话",
      "run1:assistant",
    );
    expect(twice.map((m) => m.id)).toContain("run1:assistant#t2");
    expect(twice.map((m) => m.id)).toContain("run1:assistant");
  });

  test("找不到流式助手消息时安全返回原数组", () => {
    const noAssistant: Message[] = [
      msg({ id: "u", role: "user", content: "x" }),
      msg({
        id: "steer-1",
        role: "user",
        content: "中途插话",
        metadata: { queued: true },
      }),
    ];
    expect(
      splitAssistantTurnOnSteerDelivery(noAssistant, "中途插话", "missing"),
    ).toBe(noAssistant);
  });
});
