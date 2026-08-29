/** @vitest-environment jsdom */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import type { ToolPart } from "../../../../types";
import { MessagePartRenderer } from "../MessagePartRenderer";

afterEach(cleanup);

const basePart = {
  type: "tool" as const,
  name: "read_file",
  args: {},
  isPending: true,
};

function renderPart(part: ToolPart) {
  return render(
    <MessagePartRenderer part={part} isLast={false} isStreaming={true} />,
  );
}

test("args-partial read_file renders via the dedicated item with the growing path", () => {
  renderPart({
    ...basePart,
    args: { partial: '{"file_path":"/tmp/ma' },
    argsPartial: true,
  });

  // Dedicated ReadFileItem surfaces the progressively parsed path and never
  // falls back to the generic raw-partial display.
  expect(screen.getByText(/\/tmp\/ma/)).toBeTruthy();
  expect(screen.queryByText(/\{"file_path/)).toBe(null);
});

test("args-partial execute renders via the dedicated item with the growing command", () => {
  renderPart({
    ...basePart,
    name: "execute",
    args: { partial: '{"command":"python foo' },
    argsPartial: true,
  });

  expect(screen.getByText(/python foo/)).toBeTruthy();
  expect(screen.queryByText(/\{"command/)).toBe(null);
});

test("args-partial generic tools keep the raw partial display", () => {
  renderPart({
    ...basePart,
    name: "my_server:fetch_url",
    args: { partial: '{"url":"https://example' },
    argsPartial: true,
  });

  // Generic ToolCallItem keeps its existing partial rendering contract.
  expect(screen.getByText(/\{"url":"https:\/\/example/)).toBeTruthy();
});

test("upgraded (non-partial) read_file renders via the dedicated item", () => {
  renderPart({
    ...basePart,
    id: "run-1",
    args: { file_path: "/tmp/notes.md" },
  });

  // ReadFileItem shows the file name without generic partial fallbacks.
  expect(screen.getByText(/notes\.md/)).toBeTruthy();
  expect(screen.queryByText(/\{"file_path/)).toBe(null);
});
