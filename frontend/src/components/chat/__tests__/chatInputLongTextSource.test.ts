import { existsSync, readFileSync } from "node:fs";

function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const chatInputSource = readSource("../ChatInput.tsx");
const longTextSource = readSource("../longTextConversion.ts");
const expandedSource = readSource("../ChatInputExpandedComposer.tsx");
const attachmentsSource = readSource("../ChatInputAttachments.tsx");
const sessionSource = readSource("../../../services/api/session.ts");

test("ChatInput wires long-text conversion and expanded composer", () => {
  expect(chatInputSource).toMatch(/useLongTextConversion/);
  expect(chatInputSource).toMatch(/ChatInputExpandedComposer/);
  expect(chatInputSource).toMatch(/showExpandButton/);
  expect(chatInputSource).toMatch(/onRestoreLongText/);
  expect(chatInputSource).toMatch(/prepareSubmit/);
  expect(chatInputSource).toMatch(/maybeConvertInput/);
});

test("long text conversion keeps local original text for restore only", () => {
  expect(longTextSource).toMatch(/localOriginalText/);
  expect(longTextSource).toMatch(/fromLongText/);
  expect(longTextSource).toMatch(/stripLocalAttachmentFields/);
  expect(longTextSource).not.toMatch(/DEFAULT_LONG_TEXT_MESSAGE/);
  expect(longTextSource).not.toMatch(/请查看附件中的长文本/);
});

test("expanded composer supports Esc collapse", () => {
  expect(expandedSource).toMatch(/Escape/);
  expect(expandedSource).toMatch(/onCollapse/);
  expect(expandedSource).toMatch(/useBodyScrollLock/);
});

test("attachment cards expose restore-as-text for long text uploads", () => {
  expect(attachmentsSource).toMatch(/onRestoreLongText/);
  expect(attachmentsSource).toMatch(/canRestoreLongTextAttachment/);
  expect(attachmentsSource).toMatch(/onSendAsText/);
});

test("submit chat body strips client-only long text fields", () => {
  expect(sessionSource).toMatch(/stripLocalAttachmentFields\(attachments\)/);
});

test("ChatInput stays modular under the 1000-line ceiling", () => {
  expect(chatInputSource.split("\n").length).toBeLessThan(1000);
  expect(
    existsSync(new URL("../ChatInputRunSkillsBar.tsx", import.meta.url)),
  ).toBe(true);
  expect(
    existsSync(new URL("../ChatInputExpandedComposer.tsx", import.meta.url)),
  ).toBe(true);
  expect(existsSync(new URL("../longTextConversion.ts", import.meta.url))).toBe(
    true,
  );
});
