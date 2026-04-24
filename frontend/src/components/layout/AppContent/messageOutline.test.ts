import assert from "node:assert/strict";
import test from "node:test";

import type { Message } from "../../../types";
import {
  createHeadingAnchorId,
  createMessageAnchorId,
  extractMessageOutline,
  shouldShowMessageOutline,
} from "./messageOutline.ts";

function createMessage(overrides: Partial<Message>): Message {
  return {
    id: overrides.id ?? "message-id",
    role: overrides.role ?? "assistant",
    content: overrides.content ?? "",
    timestamp: overrides.timestamp ?? new Date("2026-04-25T00:00:00.000Z"),
    ...overrides,
  };
}

test("shows the message outline only after more than three user messages", () => {
  const withThreeUserMessages = [
    createMessage({ id: "u1", role: "user", content: "One" }),
    createMessage({ id: "u2", role: "user", content: "Two" }),
    createMessage({ id: "u3", role: "user", content: "Three" }),
  ];
  const withFourUserMessages = [
    ...withThreeUserMessages,
    createMessage({ id: "u4", role: "user", content: "Four" }),
  ];

  assert.equal(shouldShowMessageOutline(withThreeUserMessages), false);
  assert.equal(shouldShowMessageOutline(withFourUserMessages), true);
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

  assert.deepEqual(extractMessageOutline(messages), [
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

  assert.deepEqual(extractMessageOutline(messages), [
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
