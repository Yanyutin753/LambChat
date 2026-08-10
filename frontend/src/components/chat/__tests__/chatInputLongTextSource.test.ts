import { existsSync, readFileSync } from "node:fs";

function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const chatInputSource = readSource("../ChatInput.tsx");
const longTextSource = readSource("../longTextConversion.ts");
const attachmentsSource = readSource("../ChatInputAttachments.tsx");
const sessionSource = readSource("../../../services/api/session.ts");

test("ChatInput uses one rich composer for inline long-text references", () => {
  expect(chatInputSource).toMatch(/useLongTextConversion/);
  expect(chatInputSource).toMatch(/RichChatComposer/);
  expect(chatInputSource.match(/<RichChatComposer\s/g)).toHaveLength(1);
  expect(chatInputSource).toMatch(/showExpandButton/);
  expect(chatInputSource).toMatch(/onRestoreLongText/);
  expect(chatInputSource).toMatch(/prepareSubmit/);
  expect(chatInputSource).toMatch(
    /buildLongTextClientMeta\(\s*payload\.originalText,\s*payload\.referenceId/,
  );
  expect(chatInputSource).toMatch(/visibleAttachments/);
  expect(chatInputSource).not.toMatch(/maybeConvertInput/);
  expect(chatInputSource).not.toMatch(/<textarea/);
});

test("ChatInput wires file paste to the existing upload flow", () => {
  expect(chatInputSource).toMatch(
    /filePaste=\{\{\s*validateCount,\s*onFiles: uploadFiles,?\s*\}\}/,
  );
});

test("rich composer loads outside the eager app bundle without losing the draft", () => {
  expect(chatInputSource).toMatch(/lazy\(async \(\) =>/);
  expect(chatInputSource).toMatch(
    /import\("\.\/richComposer\/RichChatComposer"\)/,
  );
  expect(chatInputSource).toMatch(/<Suspense/);
  expect(chatInputSource).toMatch(/initialPlainText=\{input\}/);
});

test("long text conversion keeps local original text for restore only", () => {
  expect(longTextSource).toMatch(/localOriginalText/);
  expect(longTextSource).toMatch(/fromLongText/);
  expect(longTextSource).toMatch(/stripLocalAttachmentFields/);
  expect(longTextSource).not.toMatch(/DEFAULT_LONG_TEXT_MESSAGE/);
  expect(longTextSource).not.toMatch(/请查看附件中的长文本/);
});

test("expanded mode preserves the mounted rich editor and supports Esc", () => {
  expect(chatInputSource).toMatch(/data-composer-expanded/);
  expect(chatInputSource).toMatch(/useBodyScrollLock\(composerExpanded\)/);
  expect(chatInputSource).toMatch(/event\.key !== "Escape"/);
  expect(chatInputSource).toMatch(/enabled: !composerExpanded/);
  expect(chatInputSource.match(/<RichChatComposer\s/g)).toHaveLength(1);
});

test("expanded composer exposes an accessible collapse action", () => {
  expect(chatInputSource).toMatch(/chat\.collapseComposer/);
  expect(chatInputSource).toMatch(/setComposerExpanded\(false\)/);
  expect(chatInputSource).toMatch(/<Minimize2/);
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
  ).toBe(false);
  expect(
    existsSync(new URL("../ChatInputExpandedComposer.tsx", import.meta.url)),
  ).toBe(false);
  expect(
    existsSync(
      new URL("../richComposer/RichChatComposer.tsx", import.meta.url),
    ),
  ).toBe(true);
  expect(existsSync(new URL("../longTextConversion.ts", import.meta.url))).toBe(
    true,
  );
});
