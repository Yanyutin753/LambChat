/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";
import i18n from "../../i18n";
import { EditorSidebar } from "../../components/common/EditorSidebar";
import { resetRightPanelCoordinator } from "../../components/common/rightPanelCoordinator";
import { useRightPanelState } from "../useRightPanelState";

beforeEach(() => {
  resetRightPanelCoordinator();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});
afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});

test.each([
  [false, true],
  [null, { id: "same-record" }],
  [undefined, null],
])(
  "repeated open restores a retained panel with closed state %s",
  (closed, opened) => {
    function Harness() {
      const [value, setValue] = useRightPanelState<unknown>(
        "editor:test",
        closed,
      );
      const [other, setOther] = useRightPanelState("editor:other", false);
      return (
        <>
          <button onClick={() => setValue(opened)}>Open editor</button>
          <button onClick={() => setOther(true)}>Open other</button>
          <EditorSidebar
            registryKey="editor:test"
            open={value !== closed}
            onClose={() => setValue(closed)}
            title="Editor"
          >
            <input aria-label="Draft" defaultValue="unsaved" />
          </EditorSidebar>
          <EditorSidebar
            registryKey="editor:other"
            open={other}
            onClose={() => setOther(false)}
            title="Other"
          >
            Other content
          </EditorSidebar>
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open editor" }));
    const draft = screen.getByRole("textbox", { name: "Draft" });
    fireEvent.change(draft, { target: { value: "kept" } });
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.collapsePanel") }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Open editor" }));
    expect(screen.getByRole("textbox", { name: "Draft" })).toBe(draft);
    expect(draft).toHaveValue("kept");

    fireEvent.click(screen.getByRole("button", { name: "Open other" }));
    expect(screen.queryByRole("textbox", { name: "Draft" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open editor" }));
    expect(screen.getByRole("textbox", { name: "Draft" })).toBe(draft);
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    fireEvent.click(
      screen.getByRole("button", {
        name: i18n.t("common.closePanelTab", { title: "Other" }),
      }),
    );
    expect(screen.getByRole("textbox", { name: "Draft" })).toBe(draft);
  },
);
