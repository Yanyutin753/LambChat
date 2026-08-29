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

test("args-partial tool parts render via the generic partial display", () => {
  renderPart({
    ...basePart,
    args: { partial: '{"file_path":"/tmp' },
    argsPartial: true,
  });

  // Generic ToolCallItem formats the tool name (Read File) and surfaces the
  // partial args text in the pill summary.
  expect(screen.getByText(/read_file/i)).toBeTruthy();
  expect(screen.getByText(/\{"file_path":"\/tmp/)).toBeTruthy();
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
