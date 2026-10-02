/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { FileContextMenu } from "../components/FileContextMenu";
import { DropdownShell } from "../components/DropdownShell";
import type { RevealedFileItem } from "../../../services/api";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("file actions escape the grid and preview stacking context", () => {
  const file = {
    session_id: "session",
    file_name: "report.md",
  } as RevealedFileItem;
  const { container } = render(
    <div className="auto-grid-cols overflow-hidden">
      <FileContextMenu
        menu={{ x: 500, y: 200, file }}
        menuId="file-menu"
        onClose={vi.fn()}
        file={file}
        onGoToSession={vi.fn()}
        onToggleFavorite={vi.fn()}
      />
    </div>,
  );
  const menu = screen.getByRole("menu", { name: "report.md" });
  expect(menu.parentElement).toBe(document.body);
  expect(container.contains(menu)).toBe(false);
});

test("file toolbar dropdown escapes its clipping panel", () => {
  render(
    <DropdownShell
      show
      onClose={vi.fn()}
      pos={{ top: 100, left: 20, right: 20 }}
      align="left"
      w="w-60"
    >
      <button>Sort files</button>
    </DropdownShell>,
  );
  expect(
    screen.getByRole("button", { name: "Sort files" }).parentElement
      ?.parentElement,
  ).toBe(document.body);
});
