import { expect, test } from "vitest";
import { processMessageEvent } from "../eventProcessor";
import { reconstructMessagesFromEvents } from "../historyLoader";
import { updateToolResultInPartsById } from "../messageParts";
import type { HistoryEvent } from "../types";

const command = 'curl -s -w "%{http_code}" https://example.com/';

// A result may arrive without tool:start, and may use the backend's new ID.
test.each(["draft", "tools:execution"])(
  "live and replay preserve streamed command when result ID is %s",
  (resultId) => {
    const events: HistoryEvent[] = [
      {
        event_type: "tool:args:chunk",
        run_id: "run",
        data: {
          tool: "execute",
          tool_call_id: "draft",
          content: JSON.stringify({ command }),
        },
      },
      {
        event_type: "tool:result",
        run_id: "run",
        data: {
          tool: "execute",
          tool_call_id: resultId,
          result: "[Command succeeded with exit code 0]",
          success: true,
        },
      },
    ];
    let parts = processMessageEvent(
      "tool:args:chunk",
      events[0].data,
      [],
      "",
      [],
      0,
      [],
      true,
    ).parts;
    parts = processMessageEvent(
      "tool:result",
      events[1].data,
      parts,
      "",
      [],
      0,
      [],
      true,
    ).parts;
    const history = reconstructMessagesFromEvents(events, new Set(), {
      activeSubagentStack: [],
    });
    for (const rendered of [parts, history[0].parts]) {
      expect(rendered).toHaveLength(1);
      expect(rendered?.[0]).toMatchObject({
        type: "tool",
        args: { command },
        isPending: false,
        success: true,
      });
      expect(rendered?.[0]).not.toMatchObject({ argsPartial: true });
    }
  },
);

test("nested result updates preserve streamed arguments", () => {
  const parts = updateToolResultInPartsById(
    [
      {
        type: "tool",
        id: "draft",
        name: "execute",
        args: { partial: JSON.stringify({ command }) },
        argsPartial: true,
        isPending: true,
      },
    ],
    "draft",
    "done",
    true,
  );
  expect(parts?.[0]).toMatchObject({ args: { command }, argsPartial: false });
});

test("authoritative start arguments replace the streamed draft", () => {
  const draft = processMessageEvent(
    "tool:args:chunk",
    { tool: "execute", tool_call_id: "draft", content: '{"command":"old' },
    [],
    "",
    [],
    0,
    [],
    true,
  ).parts;
  const started = processMessageEvent(
    "tool:start",
    {
      tool: "execute",
      tool_call_id: "execution",
      args: { command: "printf final" },
    },
    draft,
    "",
    [],
    0,
    [],
    true,
  ).parts;
  expect(started[0]).toMatchObject({ args: { command: "printf final" } });
});
