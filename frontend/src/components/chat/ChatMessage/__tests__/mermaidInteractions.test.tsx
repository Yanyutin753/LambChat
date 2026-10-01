/** @vitest-environment jsdom */
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import mermaid from "mermaid";
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
  vi.clearAllMocks();
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

const clipboard = vi.hoisted(() => ({
  copy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("../../../../utils/clipboard", () => ({
  copyToClipboard: clipboard.copy,
}));
vi.mock("react-hot-toast", () => ({
  default: { success: clipboard.success, error: clipboard.error },
}));

test.each([false, true])(
  "diagram copy waits for confirmation (fullscreen=%s)",
  async (fullscreen) => {
    let complete!: () => void;
    clipboard.copy.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          complete = resolve;
        }),
    );
    render(<MermaidDiagram chart="graph LR; A-->B" />);
    await screen.findByRole("button", { name: "imageViewer.fullscreen" });
    if (fullscreen)
      fireEvent.click(
        screen.getByRole("button", { name: "imageViewer.fullscreen" }),
      );
    const scope = fullscreen
      ? within(screen.getByRole("dialog", { name: "chat.mermaidDiagram" }))
      : screen;
    const button = scope.getByRole("button", { name: "chat.message.copyCode" });
    fireEvent.click(button);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await act(async () => complete());
    expect(
      scope.getByRole("button", { name: "chat.message.copied" }),
    ).toBeEnabled();
  },
);

test.each([false, true])(
  "diagram copy recovers from failure (fullscreen=%s)",
  async (fullscreen) => {
    clipboard.copy
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockResolvedValueOnce(undefined);
    render(<MermaidDiagram chart="graph LR; A-->B" />);
    await screen.findByRole("button", { name: "imageViewer.fullscreen" });
    if (fullscreen)
      fireEvent.click(
        screen.getByRole("button", { name: "imageViewer.fullscreen" }),
      );
    const scope = fullscreen
      ? within(screen.getByRole("dialog", { name: "chat.mermaidDiagram" }))
      : screen;
    fireEvent.click(
      scope.getByRole("button", { name: "chat.message.copyCode" }),
    );
    await waitFor(() => expect(clipboard.error).toHaveBeenCalledOnce());
    const retry = scope.getByRole("button", { name: "chat.message.copyCode" });
    expect(retry).toHaveAttribute(
      "aria-description",
      "chat.message.copyFailed",
    );
    expect(clipboard.success).not.toHaveBeenCalled();
    fireEvent.click(retry);
    await scope.findByRole("button", { name: "chat.message.copied" });
    expect(clipboard.copy).toHaveBeenLastCalledWith("graph LR; A-->B");
    expect(clipboard.success.mock.calls[0][1].id).toBe(
      clipboard.error.mock.calls[0][1].id,
    );
  },
);

test("diagram nodes and lines follow the application palette", async () => {
  const colors = {
    "--theme-bg-card": "#faf6ea",
    "--theme-text": "#342d22",
    "--theme-border": "#d8ccb3",
    "--theme-text-secondary": "#796b56",
  };
  for (const [name, value] of Object.entries(colors))
    document.documentElement.style.setProperty(name, value);
  try {
    render(<MermaidDiagram chart="graph LR; A-->B" />);
    await screen.findByRole("button", { name: "imageViewer.fullscreen" });
    expect(mermaid.initialize).toHaveBeenLastCalledWith(
      expect.objectContaining({
        theme: "base",
        themeVariables: expect.objectContaining({
          primaryColor: colors["--theme-bg-card"],
          primaryTextColor: colors["--theme-text"],
          primaryBorderColor: colors["--theme-border"],
          lineColor: colors["--theme-text-secondary"],
        }),
      }),
    );
  } finally {
    for (const name of Object.keys(colors))
      document.documentElement.style.removeProperty(name);
  }
});
