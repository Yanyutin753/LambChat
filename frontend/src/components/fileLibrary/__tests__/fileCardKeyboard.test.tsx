/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { RevealedFileCard } from "../RevealedFileCard";
import type { RevealedFileItem } from "../../../services/api";

vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../components/FileCardPreview", () => ({
  FileCardPreview: () => <span>Preview</span>,
}));
afterEach(cleanup);

test.each(["grid", "list"] as const)(
  "%s file actions support keyboard opening, selection and Escape",
  (viewMode) => {
    const preview = vi.fn();
    const go = vi.fn();
    render(
      <RevealedFileCard
        file={
          {
            session_id: "session",
            file_name: "report.md",
            created_at: "2026-10-01",
          } as RevealedFileItem
        }
        viewMode={viewMode}
        onPreview={preview}
        onGoToSession={go}
        onToggleFavorite={() => {}}
      />,
    );
    const title = screen.getByRole("button", { name: "report.md" });
    fireEvent.click(title);
    expect(preview).toHaveBeenCalledOnce();
    const card = screen.getByRole("group", { name: "report.md" });
    fireEvent.keyDown(card, { key: "F10", shiftKey: true });
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(card).toHaveFocus();
    const more = screen.getByRole("button", { name: "common.moreOptions" });
    more.focus();
    fireEvent.click(more, { detail: 0 });
    const first = screen.getByRole("menuitem", {
      name: "fileLibrary.context.goToSession",
    });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(
      screen.getByRole("menuitem", { name: "fileLibrary.context.favorite" }),
    ).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(more).toHaveFocus();
    fireEvent.click(more);
    fireEvent.click(
      screen.getByRole("menuitem", { name: "fileLibrary.context.goToSession" }),
    );
    expect(go).toHaveBeenCalledWith(
      "session",
      expect.objectContaining({ file_name: "report.md" }),
    );
    expect(screen.queryByRole("menu")).toBeNull();
    expect(preview).toHaveBeenCalledOnce();
  },
);
