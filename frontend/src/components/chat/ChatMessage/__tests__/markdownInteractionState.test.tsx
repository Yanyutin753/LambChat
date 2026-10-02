/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import appI18n from "../../../../i18n";
import { MarkdownContent } from "../MarkdownContent";

vi.mock("../../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
const clipboard = vi.hoisted(() => ({ copy: vi.fn() }));
vi.mock("../../../../utils/clipboard", () => ({
  copyToClipboard: clipboard.copy,
}));
afterEach(cleanup);

test("chat code search and copy share the toolbar beside its language label", async () => {
  const i18n = appI18n.cloneInstance({ lng: "en" });
  render(
    <I18nextProvider i18n={i18n}>
      <MarkdownContent content={"```js\nconst result = 42;\n```"} />
    </I18nextProvider>,
  );
  const search = await screen.findByRole("button", { name: "Search" });
  const copy = screen.getByRole("button", { name: "Copy code" });
  expect(search.closest(".code-editor-toolbar")).toBe(
    copy.closest(".code-editor-toolbar"),
  );
  expect(copy.closest(".code-editor-toolbar")).toHaveTextContent("js");
});

test("appending streamed Markdown and completing the run preserve code search and focus", async () => {
  const i18n = appI18n.cloneInstance({ lng: "en" });
  const content = "```js\nconst result = 42;\n```";
  const message = (body: string, streaming: boolean) => (
    <I18nextProvider i18n={i18n}>
      <MarkdownContent
        content={body}
        isStreaming={streaming}
        headingAnchorContext={{ messageId: "run-1", partIndex: 0 }}
      />
    </I18nextProvider>
  );
  const { rerender } = render(message(content, true));
  fireEvent.click(await screen.findByRole("button", { name: "Search" }));
  const query = screen.getByRole("textbox", { name: "Find" });
  fireEvent.change(query, { target: { value: "result" } });
  rerender(message(`${content}\n\n## Results\nMore detail.`, true));
  expect(screen.getByRole("textbox", { name: "Find" })).toBe(query);
  expect(query).toHaveValue("result");
  expect(document.activeElement).toBe(query);
  rerender(message(`${content}\n\n## Results\nMore detail.`, false));
  expect(screen.getByRole("textbox", { name: "Find" })).toBe(query);
  expect(query).toHaveValue("result");
  expect(document.activeElement).toBe(query);
  expect(screen.getByRole("heading", { name: "Results" })).toHaveAttribute(
    "data-outline-id",
    "chat-outline-heading-run-1-0-results",
  );
  expect(document.querySelector(".ai-code-block")).not.toHaveAttribute(
    "data-streaming",
  );
});

test("appending unrelated Markdown preserves pending table copy and its success feedback", async () => {
  let complete!: () => void;
  clipboard.copy.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  const i18n = appI18n.cloneInstance({ lng: "en" });
  const table = "| Name | Value |\n| --- | --- |\n| Draft | two |";
  const message = (content: string) => (
    <I18nextProvider i18n={i18n}>
      <MarkdownContent content={content} />
    </I18nextProvider>
  );
  const { rerender } = render(message(table));
  fireEvent.click(screen.getByRole("button", { name: "Copy" }));
  expect(screen.getByRole("button", { name: "Copy" })).toBeDisabled();
  rerender(message(`${table}\n\nMore detail.`));
  expect(screen.getByRole("button", { name: "Copy" })).toBeDisabled();
  await act(async () => complete());
  expect(screen.getByRole("button", { name: "Copied!" })).toBeEnabled();
  expect(clipboard.copy).toHaveBeenCalledWith(
    "| Name  | Value |\n| ----- | ----- |\n| Draft | two   |",
  );
});
