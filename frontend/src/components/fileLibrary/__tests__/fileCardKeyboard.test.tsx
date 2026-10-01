/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { GridCard } from "../components/GridCard";
import { ListCard } from "../components/ListCard";
import type { RevealedFileItem } from "../../../services/api";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../components/FileCardPreview", () => ({
  FileCardPreview: () => <span>Preview</span>,
}));
afterEach(cleanup);

const file = {
  id: "file",
  session_id: "session",
  file_name: "report.md",
  file_size: 100,
  created_at: "2026-10-01T00:00:00Z",
} as RevealedFileItem;

test.each([GridCard, ListCard])(
  "%s provides a file action separate from its more menu",
  (Card) => {
    const preview = vi.fn();
    render(
      <Card
        file={file}
        onPreview={preview}
        onGoToSession={vi.fn()}
        onToggleFavorite={vi.fn()}
      />,
    );
    const open = screen.getByRole("button", { name: "report.md", exact: true });
    open.focus();
    fireEvent.click(open);
    expect(preview).toHaveBeenCalledExactlyOnceWith(file);
    fireEvent.click(screen.getByRole("button", { name: /common.moreOptions/ }));
    expect(preview).toHaveBeenCalledTimes(1);
  },
);

test.each([GridCard, ListCard])(
  "%s closes its menu on Escape and restores focus",
  (Card) => {
    render(
      <Card
        file={file}
        onPreview={vi.fn()}
        onGoToSession={vi.fn()}
        onToggleFavorite={vi.fn()}
      />,
    );
    const more = screen.getByRole("button", { name: /common.moreOptions/ });
    more.focus();
    fireEvent.click(more);
    const action = screen.getByRole("menuitem", {
      name: "fileLibrary.context.goToSession",
    });
    expect(document.activeElement).toBe(action);
    fireEvent.keyDown(action, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(more);
  },
);

test("file menu closes before running its selected action", () => {
  const favorite = vi.fn();
  render(
    <GridCard
      file={file}
      onPreview={vi.fn()}
      onGoToSession={vi.fn()}
      onToggleFavorite={favorite}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /common.moreOptions/ }));
  fireEvent.click(
    screen.getByRole("menuitem", { name: "fileLibrary.context.favorite" }),
  );
  expect(favorite).toHaveBeenCalledExactlyOnceWith(file);
  expect(screen.queryByRole("menu")).toBeNull();
});
