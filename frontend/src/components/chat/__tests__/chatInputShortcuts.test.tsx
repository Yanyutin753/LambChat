/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ShortcutDialog } from "../ChatInputShortcuts";
import { CHAT_INPUT_SLASH_COMMANDS } from "../chatInputSlashCommands";
import en from "../../../i18n/locales/en.json";
import zh from "../../../i18n/locales/zh.json";
import ja from "../../../i18n/locales/ja.json";
import ko from "../../../i18n/locales/ko.json";
import ru from "../../../i18n/locales/ru.json";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

test("lists supported global, contextual and slash shortcuts", () => {
  render(<ShortcutDialog open onClose={() => {}} />);
  for (const key of [
    "toggleSidebar", "settings", "cycleTheme", "back", "forward",
    "candidatePrevious", "candidateNext", "candidateConfirm", "candidateDismiss",
    "focusNext", "focusPrevious", "menuFirst", "menuLast", "contextMenu",
    "previousImage", "nextImage", "previousTab", "nextTab", "closeTab",
    "editorFind", "editorNextMatch", "editorPreviousMatch", "editorGoToLine",
  ]) {
    expect(screen.getByText(`shortcut.${key}`)).toBeInTheDocument();
  }
  for (const command of CHAT_INPUT_SLASH_COMMANDS) {
    expect(screen.getByText(command.command)).toBeInTheDocument();
  }
});

test.each(["ctrl", "shift", "enter"])(
  "newline matches the %s send preference",
  (modifier) => {
    localStorage.setItem("newlineModifier", modifier);
    render(<ShortcutDialog open onClose={() => {}} />);
    const row = screen.getByText("shortcut.newline").parentElement!.parentElement!;
    expect(
      Array.from(row.querySelectorAll("kbd"), (key) => key.textContent),
    ).toEqual(modifier === "enter" ? ["Shift", "Enter"] : ["Enter"]);
  },
);

test.each([
  ["MacIntel", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "⌘", "Option"],
  ["Win32", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Ctrl", "Alt"],
  ["Linux x86_64", "Mozilla/5.0 (X11; Linux x86_64)", "Ctrl", "Alt"],
])("detects %s and displays its modifiers", (platform, userAgent, modifier, alt) => {
  vi.spyOn(navigator, "platform", "get").mockReturnValue(platform);
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(userAgent);
  render(<ShortcutDialog open onClose={() => {}} />);
  const row = screen.getByText("shortcut.toggleSidebar").parentElement!;
  expect(row.parentElement).toHaveTextContent(`${modifier}B`);
  const goToLine = screen.getByText("shortcut.editorGoToLine").parentElement!;
  expect(goToLine.parentElement).toHaveTextContent(`${modifier}${alt}G`);
  const back = screen.getByText("shortcut.back").parentElement!;
  expect(back.parentElement).toHaveTextContent(modifier === "⌘" ? "⌘[" : "Alt←");
});

test("all shortcut labels are translated in all five locales", () => {
  render(<ShortcutDialog open onClose={() => {}} />);
  const keys = Array.from(screen.getByRole("region").querySelectorAll("span, p, h4, div"))
    .filter((element) => element.children.length === 0)
    .map((element) => element.textContent ?? "")
    .filter((key) => key.startsWith("shortcut."))
    .map((key) => key.slice("shortcut.".length));
  for (const locale of [en, zh, ja, ko, ru]) {
    for (const key of keys) {
      expect(locale.shortcut).toHaveProperty(key, expect.any(String));
    }
  }
});
