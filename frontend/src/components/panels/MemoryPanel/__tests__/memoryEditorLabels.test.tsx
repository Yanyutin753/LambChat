/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { MemoryEditor } from "../MemoryEditor";
vi.mock("../../../common/EditorSidebar", () => ({
  EditorSidebar: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
afterEach(cleanup);
test("memory fields are named and the selected type is announced", () => {
  render(
    <MemoryEditor
      onClose={vi.fn()}
      onSaved={vi.fn()}
      relativeTime={() => ""}
    />,
  );
  for (const key of [
    "titleLabel",
    "summaryLabel",
    "contentLabel",
    "tagsLabel",
  ]) {
    expect(screen.getByLabelText(i18n.t(`memory.${key}`))).toBeTruthy();
  }
  const type = screen.getByRole("button", {
    name: i18n.t("memory.type.project"),
  });
  expect(type.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(type);
  expect(type.getAttribute("aria-pressed")).toBe("true");
});
