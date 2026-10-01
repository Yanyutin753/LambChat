/** @vitest-environment jsdom */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MermaidDiagram } from "../MermaidDiagram";
import { ModalSurface } from "../../../common/ModalSurface";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "dark",
}));
vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    parse: vi.fn(),
    render: vi.fn(async () => ({
      svg: '<svg viewBox="0 0 100 100"><rect width="100" height="100" /></svg>',
    })),
  },
}));

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  URL.createObjectURL = vi.fn(() => "blob:diagram");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("diagram export menu supports arrows and Escape without closing its parent", async () => {
  const close = vi.fn();
  render(
    <ModalSurface open onClose={close} label="Document">
      <MermaidDiagram chart="graph LR; A-->B" />
    </ModalSurface>,
  );
  const trigger = await screen.findByRole("button", {
    name: "documents.download",
  });
  fireEvent.click(trigger);
  const menu = screen.getByRole("menu", { name: "documents.download" });
  expect(within(menu).getByRole("menuitem", { name: "SVG" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
  expect(within(menu).getByRole("menuitem", { name: "PNG" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
  expect(close).not.toHaveBeenCalled();
});

test("fullscreen diagram captures focus and only its own Escape closes it", async () => {
  const close = vi.fn();
  render(
    <ModalSurface open onClose={close} label="Document">
      <MermaidDiagram chart="graph LR; A-->B" />
    </ModalSurface>,
  );
  const opener = await screen.findByRole("button", {
    name: "imageViewer.fullscreen",
  });
  opener.focus();
  fireEvent.click(opener);
  const viewer = screen.getByRole("dialog", { name: "chat.mermaidDiagram" });
  expect(viewer).toHaveFocus();
  fireEvent.keyDown(viewer, { key: "Escape", isComposing: true });
  expect(viewer).toBeInTheDocument();
  fireEvent.keyDown(viewer, { key: "Escape" });
  expect(
    screen.queryByRole("dialog", { name: "chat.mermaidDiagram" }),
  ).toBeNull();
  expect(screen.getByRole("dialog", { name: "Document" })).toBeInTheDocument();
  expect(close).not.toHaveBeenCalled();
  expect(opener).toHaveFocus();
});
