import { readFileSync } from "node:fs";
import type { Message } from "../../../../types";
import {
  createHeadingAnchorId,
  createMessageAnchorId,
  extractMessageOutline,
  getOutlineActiveAnchorIdForRange,
  getOutlineFlowActiveAnchorId,
  shouldShowMessageOutline,
} from "../messageOutline.ts";

function createMessage(overrides: Partial<Message>): Message {
  return {
    id: overrides.id ?? "message-id",
    role: overrides.role ?? "assistant",
    content: overrides.content ?? "",
    timestamp: overrides.timestamp ?? new Date("2026-04-25T00:00:00.000Z"),
    ...overrides,
  };
}

test("shows the message outline as soon as there is at least one user message", () => {
  const withNoUserMessages = [
    createMessage({ id: "a1", role: "assistant", content: "Hello" }),
  ];
  const withOneUserMessage = [
    createMessage({ id: "u1", role: "user", content: "One" }),
  ];

  expect(shouldShowMessageOutline(withNoUserMessages)).toBe(false);
  expect(shouldShowMessageOutline(withOneUserMessage)).toBe(true);
});

test("extracts user summaries and assistant markdown headings in message order", () => {
  const messages: Message[] = [
    createMessage({
      id: "u1",
      role: "user",
      content: "请先总结一下这次会议\n第二行不应该被拿来当标题",
    }),
    createMessage({
      id: "a1",
      role: "assistant",
      content: "# 总览\n正文\n## 关键风险\n更多内容",
    }),
    createMessage({
      id: "u2",
      role: "user",
      content:
        "这个用户消息非常长，需要被截断以便在右侧目录中更容易阅读和显示完整结构",
    }),
    createMessage({
      id: "a2",
      role: "assistant",
      parts: [
        {
          type: "thinking",
          content: "ignore me",
        },
        {
          type: "text",
          content: "### 执行步骤\n1. 准备\n2. 发布",
        },
      ],
    }),
  ];

  expect(extractMessageOutline(messages)).toEqual([
    {
      id: "message:u1",
      anchorId: createMessageAnchorId("u1"),
      kind: "user-message",
      label: "请先总结一下这次会议",
      level: 1,
      messageId: "u1",
      messageIndex: 0,
    },
    {
      id: "assistant:a1",
      anchorId: createMessageAnchorId("a1"),
      kind: "assistant-message",
      label: "# 总览",
      level: 1,
      messageId: "a1",
      messageIndex: 1,
    },
    {
      id: "heading:a1:0:总览",
      anchorId: createHeadingAnchorId({
        messageId: "a1",
        partIndex: 0,
        headingText: "总览",
      }),
      kind: "assistant-heading",
      label: "总览",
      level: 1,
      messageId: "a1",
      messageIndex: 1,
    },
    {
      id: "heading:a1:0:关键风险",
      anchorId: createHeadingAnchorId({
        messageId: "a1",
        partIndex: 0,
        headingText: "关键风险",
      }),
      kind: "assistant-heading",
      label: "关键风险",
      level: 2,
      messageId: "a1",
      messageIndex: 1,
    },
    {
      id: "message:u2",
      anchorId: createMessageAnchorId("u2"),
      kind: "user-message",
      label: "这个用户消息非常长，需要被截断以便在右侧目录中更…",
      level: 1,
      messageId: "u2",
      messageIndex: 2,
    },
    {
      id: "assistant:a2",
      anchorId: createMessageAnchorId("a2"),
      kind: "assistant-message",
      label: "### 执行步骤",
      level: 1,
      messageId: "a2",
      messageIndex: 3,
    },
    {
      id: "heading:a2:1:执行步骤",
      anchorId: createHeadingAnchorId({
        messageId: "a2",
        partIndex: 1,
        headingText: "执行步骤",
      }),
      kind: "assistant-heading",
      label: "执行步骤",
      level: 3,
      messageId: "a2",
      messageIndex: 3,
    },
  ]);
});

test("ignores headings inside fenced code blocks", () => {
  const messages: Message[] = [
    createMessage({
      id: "a1",
      role: "assistant",
      content: "```md\n# fake heading\n```\n## Real Heading",
    }),
  ];

  expect(extractMessageOutline(messages)).toEqual([
    {
      id: "assistant:a1",
      anchorId: createMessageAnchorId("a1"),
      kind: "assistant-message",
      label: "## Real Heading",
      level: 1,
      messageId: "a1",
      messageIndex: 0,
    },
    {
      id: "heading:a1:0:Real Heading",
      anchorId: createHeadingAnchorId({
        messageId: "a1",
        partIndex: 0,
        headingText: "Real Heading",
      }),
      kind: "assistant-heading",
      label: "Real Heading",
      level: 2,
      messageId: "a1",
      messageIndex: 0,
    },
  ]);
});

test("maps assistant heading anchors back to their message anchor for flow focus", () => {
  const outline = extractMessageOutline([
    createMessage({
      id: "u1",
      role: "user",
      content: "生成一个好看的 mermaid",
    }),
    createMessage({
      id: "a1",
      role: "assistant",
      content: "# 总览\n正文\n## 细节\n更多内容",
    }),
  ]);

  expect(
    getOutlineFlowActiveAnchorId(
      outline,
      createHeadingAnchorId({
        messageId: "a1",
        partIndex: 0,
        headingText: "细节",
      }),
    ),
  ).toBe(createMessageAnchorId("a1"));
});

test("maps the first visible message index to its outline anchor", () => {
  const messages: Message[] = [
    createMessage({ id: "u1", role: "user", content: "one" }),
    createMessage({ id: "a1", role: "assistant", content: "two" }),
    createMessage({ id: "u2", role: "user", content: "three" }),
  ];

  expect(
    getOutlineActiveAnchorIdForRange(messages, {
      startIndex: 1,
      endIndex: 2,
    }),
  ).toBe(createMessageAnchorId("a1"));
});

test("mobile message outline opens in a full-height viewport panel", () => {
  const source = readFileSync(
    new URL("../useChatOutline.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/mobileFillViewport:\s*isMobile/);
});
