/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { lazy, Suspense } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import appI18n from "../../../i18n";
import { useDocumentPreviewState } from "../useDocumentPreviewState";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import DocumentPreviewContent from "../DocumentPreviewContent";
import HtmlPreview from "../previews/HtmlPreview";
import type { CodeMirrorViewerProps } from "../../common/CodeMirrorViewer";

const previewLoad = vi.hoisted(() => ({
  pending: false,
  release: undefined as undefined | (() => void),
}));
vi.mock("../../common/DeferredCodeMirrorViewer", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("../../common/DeferredCodeMirrorViewer")
    >();
  const DelayedViewer = lazy(
    () =>
      new Promise<{ default: typeof actual.DeferredCodeMirrorViewer }>(
        (resolve) => {
          previewLoad.release = () =>
            resolve({ default: actual.DeferredCodeMirrorViewer });
        },
      ),
  );
  return {
    DeferredCodeMirrorViewer: (props: CodeMirrorViewerProps) =>
      previewLoad.pending ? (
        <Suspense fallback={<div role="status">Loading code preview</div>}>
          <DelayedViewer {...props} />
        </Suspense>
      ) : (
        <actual.DeferredCodeMirrorViewer {...props} />
      ),
  };
});

vi.mock("../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
beforeEach(() => {
  previewLoad.pending = false;
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});

test("file search waits for the lazy viewer instead of accepting a silent no-op", async () => {
  previewLoad.pending = true;
  const i18n = appI18n.cloneInstance({ lng: "zh" });
  render(
    <I18nextProvider i18n={i18n}>
      <Preview />
    </I18nextProvider>,
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Loading code preview",
  );
  expect(screen.getByRole("button", { name: "搜索" })).toBeDisabled();
  await act(async () => previewLoad.release?.());
  await screen.findByRole("textbox", { name: "代码预览" });
  expect(screen.getByRole("button", { name: "搜索" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  expect(
    await screen.findByRole(
      "textbox",
      { name: "查找" },
      // CI runners load the search extension module cold; the default 1s
      // findByRole budget times out there while local runs stay warm.
      { timeout: 8000 },
    ),
  ).toHaveFocus();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Preview({ fullscreen = false }: { fullscreen?: boolean }) {
  const state = useDocumentPreviewState({
    path: "example.py",
    content: "alpha = 1\nalpha = 2",
    onClose: vi.fn(),
  });
  return (
    <div ref={state.panelRef}>
      <DocumentPreviewToolbar {...state} isFullscreen={fullscreen} embedded />
      <DocumentPreviewContent {...state} />
    </div>
  );
}

test.each([false, true])(
  "file preview opens native find without a second toolbar (fullscreen=%s)",
  async (fullscreen) => {
    const { container } = render(
      <I18nextProvider i18n={appI18n.cloneInstance({ lng: "zh" })}>
        <Preview fullscreen={fullscreen} />
      </I18nextProvider>,
    );
    await screen.findByRole("textbox", { name: "代码预览" });
    expect(container.querySelector(".code-editor-toolbar")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    const field = await screen.findByRole("textbox", { name: "查找" });
    expect(field).toHaveFocus();
    fireEvent.change(field, { target: { value: "alpha" } });
    fireEvent.click(
      container.querySelector<HTMLButtonElement>('.cm-search [name="close"]')!,
    );
    const editor = screen.getByRole("textbox", { name: "代码预览" });
    expect(editor).toHaveFocus();
    expect(editor.textContent).toBe("alpha = 1alpha = 2");
    fireEvent.keyDown(editor, { key: "f", code: "KeyF", ctrlKey: true });
    expect(await screen.findByRole("textbox", { name: "查找" })).toBeTruthy();
  },
);

test("HTML source search shares its existing source toolbar", async () => {
  const { container } = render(
    <I18nextProvider i18n={appI18n.cloneInstance({ lng: "zh" })}>
      <HtmlPreview content="<p>alpha</p>" />
    </I18nextProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "源码" }));
  await screen.findByRole("textbox", { name: "代码预览" });
  expect(container.querySelector(".code-editor-toolbar")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  expect(
    await screen.findByRole(
      "textbox",
      { name: "查找" },
      // CI runners load the search extension module cold; the default 1s
      // findByRole budget times out there while local runs stay warm.
      { timeout: 8000 },
    ),
  ).toHaveFocus();
});
