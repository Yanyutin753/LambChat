import type { Message } from "../../../types/message";
import { splitAssistantTurn } from "../steerTurnSplit";

function msg(
  partial: Partial<Message> & Pick<Message, "id" | "role">,
): Message {
  return { content: "", timestamp: new Date(), ...partial } as Message;
}

describe("splitAssistantTurn", () => {
  test("封存当前流式助手轮次并追加新轮次（沿用原 id 接收后续事件）", () => {
    const base: Message[] = [
      msg({ id: "u1", role: "user", content: "任务" }),
      msg({
        id: "a1",
        role: "assistant",
        content: "第一轮",
        isStreaming: true,
        parts: [],
      }),
    ];

    const result = splitAssistantTurn(base, "a1");

    expect(result.map((m) => m.id)).toEqual(["u1", "a1#t1", "a1"]);
    expect(result[1].isStreaming).toBe(false);
    expect(result[2].role).toBe("assistant");
    expect(result[2].isStreaming).toBe(true);
    expect(result[2].parts).toEqual([]);
  });

  test("多次分割递增后缀", () => {
    const once = splitAssistantTurn(
      [
        msg({ id: "u", role: "user" }),
        msg({ id: "a1", role: "assistant", isStreaming: true }),
      ],
      "a1",
    );
    // 模拟新轮次继续流式后再分割
    const twice = splitAssistantTurn(once, "a1");
    expect(twice.map((m) => m.id)).toContain("a1#t2");
    expect(twice.map((m) => m.id).filter((id) => id === "a1")).toHaveLength(1);
  });

  test("找不到助手消息时返回原数组", () => {
    const base: Message[] = [msg({ id: "u", role: "user" })];
    expect(splitAssistantTurn(base, "missing")).toBe(base);
  });
});
