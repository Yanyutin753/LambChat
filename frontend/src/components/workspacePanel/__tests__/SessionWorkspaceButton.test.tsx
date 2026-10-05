/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { SessionWorkspaceButton } from "../SessionWorkspaceButton";
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../WorkspacePanel", async () => {
  const { useState } = await import("react");
  const { ToolResultPanel } = await import(
    "../../chat/ChatMessage/items/ToolResultPanel"
  );
  return {
    WorkspacePanel: ({ sessionId }: { sessionId: string }) => {
      const [preview, setPreview] = useState(false);
      return (
        <>
          <div>files for {sessionId}</div>
          <button onClick={() => setPreview(true)}>Preview file</button>
          {preview && (
            <ToolResultPanel
              open
              onClose={() => setPreview(false)}
              title="Preview"
              registryKey="test-preview"
            >
              File content
            </ToolResultPanel>
          )}
        </>
      );
    },
  };
});
beforeAll(async () => {
  // Keep cold compilation of the real panel outside interaction timeouts.
  // SessionWorkspaceButton still loads and renders it lazily after the click.
  await import("../../chat/ChatMessage/items/ToolResultPanel");
}, 30_000);
afterEach(cleanup);
Object.defineProperty(window, "innerWidth", {
  configurable: true,
  value: 1440,
});

test("workspace is absent before a conversation and loads only when opened", async () => {
  const { rerender } = render(<SessionWorkspaceButton sessionId={null} />);
  expect(screen.queryByRole("button")).toBeNull();
  rerender(<SessionWorkspaceButton sessionId="a" />);
  expect(screen.queryByText("files for a")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "workspacePanel.title" }));
  expect(
    await screen.findByText("files for a", {}, { timeout: 5000 }),
  ).toBeVisible();
  expect(
    screen.getByRole("complementary", { name: "workspacePanel.title" }),
  ).toBeVisible();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByText("files for a")).toBeNull();
});

test("switching conversations closes the previous workspace", async () => {
  const { rerender } = render(<SessionWorkspaceButton sessionId="a" />);
  fireEvent.click(screen.getByRole("button", { name: "workspacePanel.title" }));
  await screen.findByText("files for a", {}, { timeout: 5000 });
  rerender(<SessionWorkspaceButton sessionId="b" />);
  expect(screen.queryByText("files for a")).toBeNull();
  expect(screen.queryByText("files for b")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "workspacePanel.title" }));
  expect(await screen.findByText("files for b")).toBeVisible();
});

test("narrow screens open files as a modal with a working close control", async () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  render(<SessionWorkspaceButton sessionId="mobile" />);
  fireEvent.click(screen.getByRole("button", { name: "workspacePanel.title" }));
  expect(
    await screen.findByRole("dialog", { name: "workspacePanel.title" }),
  ).toHaveAttribute("aria-modal", "true");
  fireEvent.click(screen.getByRole("button", { name: "common.close" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});

test("files and previews share width, including resize then return", async () => {
  localStorage.setItem("sidebar-preview-width", "42");
  render(<SessionWorkspaceButton sessionId="s" />);
  fireEvent.click(screen.getByRole("button", { name: "workspacePanel.title" }));
  const files = await screen.findByRole("complementary", {
    name: "workspacePanel.title",
  });
  const width = () =>
    document.documentElement.style.getPropertyValue(
      "--right-panel-active-width",
    );
  const separator = within(files).getByRole("separator");
  expect(separator).toHaveAttribute("aria-valuenow", "42");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Preview file" })).toBeVisible(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Preview file" }));
  const preview = await screen.findByRole("complementary", { name: "Preview" });
  expect(within(preview).getByRole("separator")).toHaveAttribute(
    "aria-valuenow",
    "42",
  );
  fireEvent.keyDown(within(preview).getByRole("separator"), {
    key: "ArrowLeft",
  });
  const resized = within(preview)
    .getByRole("separator")
    .getAttribute("aria-valuenow");
  const previewWidth = width();
  fireEvent.click(within(preview).getByRole("button", { name: "common.back" }));
  await waitFor(() => expect(files).toBeVisible());
  expect(within(files).getByRole("separator")).toHaveAttribute(
    "aria-valuenow",
    resized,
  );
  expect(width()).toBe(previewWidth);
  localStorage.removeItem("sidebar-preview-width");
});

test.each([390, 768, 1440])(
  "files and preview share responsive presentation at %i pixels",
  async (viewport) => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: viewport,
    });
    render(<SessionWorkspaceButton sessionId="responsive" />);
    fireEvent.click(
      screen.getByRole("button", { name: "workspacePanel.title" }),
    );
    const role = viewport >= 1200 ? "complementary" : "dialog";
    const files = await screen.findByRole(role, {
      name: "workspacePanel.title",
    });
    const presentation =
      viewport < 640 ? "fullscreen" : viewport < 1200 ? "overlay" : "docked";
    expect(files).toHaveAttribute("data-panel-presentation", presentation);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Preview file" }),
      ).toBeVisible(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview file" }));
    const preview = await screen.findByRole(role, { name: "Preview" });
    expect(preview).toHaveAttribute("data-panel-presentation", presentation);
    fireEvent.click(
      within(preview).getByRole("button", { name: "common.back" }),
    );
    await waitFor(() => expect(files).toBeVisible());
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1440,
    });
  },
);
