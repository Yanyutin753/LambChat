import { expect, test } from "vitest";
import { prepareMessagesForRunningRun, reconstructMessagesFromEvents } from "../historyLoader";
import { createOptimisticMessagesForSend } from "../optimisticMessages";
import { splitAssistantTurn } from "../steerTurnSplit";

test("each historical run retains its own assistant identity", () => {
  const events = [
    { event_type: "user:message", run_id: "one", data: { content: "first", assistant_identity: { seed: "fast", name: "快速助手", avatar: null } } },
    { event_type: "message:chunk", run_id: "one", data: { content: "first reply", agent_id: "fast" } },
    { event_type: "done", run_id: "one", data: {} },
    { event_type: "user:message", run_id: "two", data: { content: "second", assistant_identity: { seed: "search", name: "搜索助手", avatar: "🤖" } } },
    { event_type: "message:chunk", run_id: "two", data: { content: "second reply", agent_id: "search" } },
    { event_type: "done", run_id: "two", data: {} },
  ];
  const messages = reconstructMessagesFromEvents(events, new Set<string>(), { activeSubagentStack: [] });
  expect(messages.filter(m => m.role === "assistant").map(m => m.assistantIdentity)).toEqual([
    { seed: "fast", name: "快速助手", avatar: null },
    { seed: "search", name: "搜索助手", avatar: "🤖" },
  ]);
});

test("old histories use their recorded main agent and ignore subagent identities", () => {
  const messages = reconstructMessagesFromEvents([
    { event_type: "metadata", run_id: "one", data: { agent_id: "fast", agent_name: "Fast Agent" } },
    { event_type: "message:chunk", run_id: "one", data: { content: "reply", agent_id: "fast" } },
    { event_type: "agent:call", run_id: "one", data: { agent_id: "child", depth: 1 } },
    { event_type: "done", run_id: "one", data: {} },
  ], new Set<string>(), { activeSubagentStack: [] });
  expect(messages[0].assistantIdentity?.seed).toBe("fast");
});

test("new submissions and steer turns preserve the captured identity", () => {
  const identity = { seed: "fast", name: "快速助手", avatar: null };
  const result = createOptimisticMessagesForSend({ previousMessages: [], content: "hello", assistantIdentity: identity });
  const split = splitAssistantTurn(result.messages, result.assistantMessageId);
  expect(split.filter(m => m.role === "assistant").map(m => m.assistantIdentity)).toEqual([identity, identity]);
});


test("an accepted run restores its snapshot before the first assistant event", () => {
  const messages = reconstructMessagesFromEvents([
    { event_type: "user:message", run_id: "run", data: { content: "hello", assistant_identity: { seed: "fast", name: "Original", avatar: null } } },
  ], new Set<string>(), { activeSubagentStack: [] });
  const prepared = prepareMessagesForRunningRun(messages, "run");
  expect(prepared.messages.find(message => message.role === "assistant")?.assistantIdentity).toEqual({ seed: "fast", name: "Original", avatar: null });
});
