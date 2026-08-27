import { describe, expect, test } from "vitest";
import type { Message, MessagePart } from "../../../../types";
import {
  countRunSteps,
  formatElapsedCompact,
  formatElapsedHuman,
  getRunElapsedMs,
  getRunStartedAtMs,
  splitRunTailGroups,
  type RunPartGroup,
} from "../runStepsCollapse";

function text(content: string): MessagePart {
  return { type: "text", content };
}

function tool(name = "execute", startedAt?: string, completedAt?: string) {
  return {
    type: "tool" as const,
    name,
    args: {},
    startedAt,
    completedAt,
  };
}

function thinking(): MessagePart {
  return { type: "thinking", content: "hmm" };
}

function group(part: MessagePart, partIndex: number): RunPartGroup {
  return { type: "single", part, partIndex };
}

function gallery(startPartIndex: number): RunPartGroup {
  return { type: "gallery", images: [], startPartIndex };
}

describe("splitRunTailGroups", () => {
  test("keeps everything in the tail when collapse is disabled (streaming)", () => {
    const groups = [
      group(thinking(), 0),
      group(tool(), 1),
      group(text("hi"), 2),
    ];
    const result = splitRunTailGroups(groups, { enabled: false });
    expect(result.head).toEqual([]);
    expect(result.tail).toHaveLength(3);
  });

  test("collapses everything before the last text part", () => {
    const groups = [
      group(thinking(), 0),
      group(tool(), 1),
      group(text("middle"), 2),
      group(tool(), 3),
      group(text("final"), 4),
    ];
    const result = splitRunTailGroups(groups, { enabled: true });
    expect(result.head).toEqual([
      group(thinking(), 0),
      group(tool(), 1),
      group(text("middle"), 2),
      group(tool(), 3),
    ]);
    expect(result.tail).toEqual([group(text("final"), 4)]);
  });

  test("keeps trailing cancelled parts visible in the tail", () => {
    const groups = [
      group(tool(), 0),
      group(text("partial"), 1),
      group({ type: "cancelled" }, 2),
    ];
    const result = splitRunTailGroups(groups, { enabled: true });
    expect(result.head).toEqual([group(tool(), 0)]);
    expect(result.tail).toEqual([
      group(text("partial"), 1),
      group({ type: "cancelled" }, 2),
    ]);
  });

  test("without any text part, only trailing cancelled parts stay visible", () => {
    const groups = [
      group(tool(), 0),
      group(thinking(), 1),
      group({ type: "cancelled" }, 2),
    ];
    const result = splitRunTailGroups(groups, { enabled: true });
    expect(result.head).toEqual([group(tool(), 0), group(thinking(), 1)]);
    expect(result.tail).toEqual([group({ type: "cancelled" }, 2)]);
  });

  test("does not collapse when there is nothing before the final text", () => {
    const groups = [group(text("only"), 0)];
    const result = splitRunTailGroups(groups, { enabled: true });
    expect(result.head).toEqual([]);
    expect(result.tail).toEqual(groups);
  });

  test("keeps image galleries intact when splitting", () => {
    const groups = [gallery(0), gallery(1), group(text("final"), 2)];
    const result = splitRunTailGroups(groups, { enabled: true });
    expect(result.head).toEqual([gallery(0), gallery(1)]);
    expect(result.tail).toEqual([group(text("final"), 2)]);
  });
});

describe("countRunSteps", () => {
  test("counts visible work parts but not text/artifact/usage parts", () => {
    const parts: MessagePart[] = [
      thinking(),
      tool(),
      { type: "text", content: "hi" },
      {
        type: "artifact",
        artifact: {
          kind: "file",
          id: "f1",
          name: "a",
          path: "/a",
          preview: { kind: "file", previewKey: "k", filePath: "/a" },
        },
      },
      {
        type: "token_usage",
        input_tokens: 1,
        output_tokens: 2,
        total_tokens: 3,
      },
      { type: "cancelled" },
      { type: "recommend_questions", questions: [] },
    ];
    expect(countRunSteps(parts)).toBe(2);
  });

  test("counts sandbox/todo/summary/subagent parts as steps without nested recursion", () => {
    const parts: MessagePart[] = [
      { type: "sandbox", status: "ready" },
      { type: "todo", items: [] },
      { type: "summary", content: "s" },
      {
        type: "subagent",
        agent_id: "a1",
        agent_name: "worker",
        input: "go",
        depth: 1,
        parts: [tool(), tool()],
      },
    ];
    expect(countRunSteps(parts)).toBe(4);
  });
});

describe("formatElapsedCompact", () => {
  test("mirrors codex compact formatting", () => {
    expect(formatElapsedCompact(0)).toBe("0s");
    expect(formatElapsedCompact(45)).toBe("45s");
    expect(formatElapsedCompact(60)).toBe("1m 00s");
    expect(formatElapsedCompact(95)).toBe("1m 35s");
    expect(formatElapsedCompact(3600)).toBe("1h 00m 00s");
    expect(formatElapsedCompact(3700)).toBe("1h 01m 40s");
  });
});

describe("formatElapsedHuman", () => {
  test("formats natural-language durations", () => {
    expect(formatElapsedHuman(0)).toBe("0 秒");
    expect(formatElapsedHuman(42)).toBe("42 秒");
    expect(formatElapsedHuman(60)).toBe("1 分");
    expect(formatElapsedHuman(597)).toBe("9 分 57 秒");
    expect(formatElapsedHuman(3600)).toBe("1 小时");
    expect(formatElapsedHuman(3723)).toBe("1 小时 2 分 3 秒");
  });
});

describe("getRunElapsedMs", () => {
  test("prefers message.duration when present", () => {
    expect(getRunElapsedMs({ duration: 123000, parts: [] } as Message)).toBe(
      123000,
    );
  });

  test("derives elapsed from tool part timestamps", () => {
    const message = {
      parts: [
        tool("a", "2026-08-26T09:00:00Z", "2026-08-26T09:00:20Z"),
        tool("b", "2026-08-26T09:00:10Z", "2026-08-26T09:00:35Z"),
      ],
    } as unknown as Message;
    expect(getRunElapsedMs(message)).toBe(35000);
  });

  test("supports subagent unix-millisecond timestamps", () => {
    const message = {
      parts: [
        {
          type: "subagent",
          agent_id: "a1",
          agent_name: "worker",
          input: "go",
          depth: 1,
          startedAt: 1000,
          completedAt: 4200,
        },
      ],
    } as unknown as Message;
    expect(getRunElapsedMs(message)).toBe(3200);
  });

  test("returns null when no timing information exists", () => {
    expect(getRunElapsedMs({ parts: [text("hi")] } as Message)).toBeNull();
  });
});

describe("getRunStartedAtMs", () => {
  test("uses the earliest part timestamp as the run start", () => {
    const message = {
      parts: [
        tool("a", "2026-08-26T09:00:10Z", "2026-08-26T09:00:20Z"),
        thinking(),
      ],
    } as unknown as Message;
    expect(getRunStartedAtMs(message)).toBe(Date.parse("2026-08-26T09:00:10Z"));
  });

  test("falls back to the message timestamp", () => {
    const message = {
      timestamp: new Date("2026-08-26T08:59:00Z"),
      parts: [text("hi")],
    } as unknown as Message;
    expect(getRunStartedAtMs(message)).toBe(Date.parse("2026-08-26T08:59:00Z"));
  });

  test("returns null when nothing is known", () => {
    expect(getRunStartedAtMs({ parts: [] } as Message)).toBeNull();
  });
});
