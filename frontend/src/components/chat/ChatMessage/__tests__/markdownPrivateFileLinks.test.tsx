/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MarkdownContent } from "../MarkdownContent";
import {
  clearRevealPreviewTabs,
  getActiveRevealPreviewState,
} from "../items/activeRevealPreviewStore";
import { setStoredServerUrl } from "../../../../services/api/serverConfig";
vi.mock("../../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
afterEach(() => {
  cleanup();
  clearRevealPreviewTabs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

test("extensionless upload links use authenticated preview instead of raw navigation", () => {
  render(
    <MarkdownContent content="[Download](/api/upload/file/uploads/opaque-key)" />,
  );
  fireEvent.click(screen.getByRole("link", { name: "Download" }));
  expect(getActiveRevealPreviewState()?.request).toMatchObject({
    kind: "file",
    signedUrl: `${window.location.origin}/api/upload/file/uploads/opaque-key`,
  });
});

test("native backend video links use the same authenticated document preview", () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  setStoredServerUrl("https://chat.example");
  render(
    <MarkdownContent content="[Video](https://chat.example/api/upload/file/uploads/video.mp4)" />,
  );
  fireEvent.click(screen.getByRole("link", { name: "Video" }));
  expect(getActiveRevealPreviewState()?.request).toMatchObject({
    kind: "file",
    signedUrl: "https://chat.example/api/upload/file/uploads/video.mp4",
  });
});
