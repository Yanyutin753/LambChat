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

  test("新轮次继承原 run 起点时间戳，插话分割后实时计时不清零", () => {
    const runStart = new Date("2026-08-26T09:00:00Z");
    const base: Message[] = [
      msg({ id: "u1", role: "user", content: "任务" }),
      msg({
        id: "a1",
        role: "assistant",
        content: "第一轮",
        isStreaming: true,
        timestamp: runStart,
        parts: [],
      }),
    ];

    const result = splitAssistantTurn(base, "a1");

    expect(result[2].timestamp).toEqual(runStart);
  });

  test("找不到助手消息时返回原数组", () => {
    const base: Message[] = [msg({ id: "u", role: "user" })];
    expect(splitAssistantTurn(base, "missing")).toBe(base);
  });

  test("封存轮次标记 cancelled（状态行切换已停止），不追加 cancelled part 组件", () => {
    const base: Message[] = [
      msg({ id: "u1", role: "user", content: "任务" }),
      msg({
        id: "a1",
        role: "assistant",
        content: "第一轮部分输出",
        isStreaming: true,
        parts: [{ type: "text", text: "第一轮部分输出" }],
      }),
    ];

    const result = splitAssistantTurn(base, "a1");

    const sealed = result[1];
    expect(sealed.id).toBe("a1#t1");
    expect(sealed.cancelled).toBe(true);
    expect(sealed.isStreaming).toBe(false);
    // 已停止是状态行文字切换（RunStepsCollapse），不是独立组件
    expect(sealed.parts?.some((part) => part.type === "cancelled")).toBe(false);
    // 新轮次不受影响
    expect(result[2].cancelled).toBeUndefined();
    expect(result[2].parts).toEqual([]);
  });

  test("封存轮次没有任何内容时不加已停止标记（避免空气泡出现已停止噪音）", () => {
    const base: Message[] = [
      msg({ id: "u1", role: "user", content: "任务" }),
      msg({ id: "a1", role: "assistant", content: "", isStreaming: true, parts: [] }),
    ];

    const result = splitAssistantTurn(base, "a1");

    expect(result[1].cancelled).toBeUndefined();
    expect(result[1].parts?.some((part) => part.type === "cancelled")).toBe(false);
  });

  test("封存轮次已有 cancelled part 时保留原状，仅补 cancelled 标志", () => {
    const base: Message[] = [
      msg({ id: "u1", role: "user", content: "任务" }),
      msg({
        id: "a1",
        role: "assistant",
        content: "半截",
        isStreaming: true,
        parts: [{ type: "text", text: "半截" }, { type: "cancelled" }],
      }),
    ];

    const result = splitAssistantTurn(base, "a1");

    expect(result[1].cancelled).toBe(true);
    const cancelledCount = result[1].parts?.filter(
      (part) => part.type === "cancelled",
    ).length;
    expect(cancelledCount).toBe(1);
  });
});
