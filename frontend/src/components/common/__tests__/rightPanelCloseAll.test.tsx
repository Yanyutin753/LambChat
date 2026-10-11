/** @vitest-environment jsdom */
import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { EditorSidebar } from "../EditorSidebar";
import { ToolResultPanel } from "../../chat/ChatMessage/items/ToolResultPanel";
import {
  getRightPanelSnapshot,
  resetRightPanelCoordinator,
} from "../rightPanelCoordinator";

afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});

test("close all from the collapsed control releases editor and result tabs", async () => {
  function Harness() {
    const [editor, setEditor] = useState(true);
    const [result, setResult] = useState(true);
    return (
      <>
        <EditorSidebar
          open={editor}
          onClose={() => setEditor(false)}
          title="Draft"
        >
          Editor content
        </EditorSidebar>
        <ToolResultPanel
          open={result}
          onClose={() => setResult(false)}
          title="Result"
        >
          Result content
        </ToolResultPanel>
      </>
    );
  }
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "Collapse panel" }));
  expect(
    screen.getByRole("button", { name: "Expand panel" }),
  ).toHaveTextContent("2");
  fireEvent.click(screen.getByRole("button", { name: "Close all tabs" }));
  await waitFor(() => expect(getRightPanelSnapshot().depth).toBe(0));
  expect(screen.queryByRole("button", { name: "Expand panel" })).toBeNull();
  expect(screen.queryByText("Editor content")).toBeNull();
  expect(screen.queryByText("Result content")).toBeNull();
});
