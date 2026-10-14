import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("shared page hides feedback and share actions on chat messages", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );
  const chatMessageSource = readFileSync(
    resolve(__dirname, "../../chat/ChatMessage/index.tsx"),
    "utf8",
  );

  expect(sharedPageSource).toMatch(/showFeedbackAndShareActions=\{false\}/);
  expect(chatMessageSource).toMatch(/showFeedbackAndShareActions\?: boolean/);
  expect(chatMessageSource).toMatch(
    /showFeedbackAndShareActions &&\s*\(\s*<>\s*\{\/\* Feedback buttons \*\//,
  );
});

test("shared page leaves each message identity to its persisted snapshot", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );

  expect(sharedPageSource).not.toMatch(/personaName=\{sharedAssistant\.name\}/);
  expect(sharedPageSource).not.toMatch(/personaAvatar=\{sharedAssistant\.avatar\}/);
  expect(sharedPageSource).toMatch(/message=\{message\}/);
});

test("share dialog supports editing existing shares without replacing the public link", () => {
  const shareDialogSource = readFileSync(
    resolve(__dirname, "../ShareDialog.tsx"),
    "utf8",
  );
  const shareApiSource = readFileSync(
    resolve(__dirname, "../../../services/api/share.ts"),
    "utf8",
  );

  expect(shareApiSource).toMatch(/async update\(/);
  expect(shareApiSource).toMatch(/method: "PATCH"/);
  expect(shareDialogSource).toMatch(/editingShare/);
  expect(shareDialogSource).toMatch(/handleEditShare/);
  expect(shareDialogSource).toMatch(/handleSaveShare/);
  expect(shareDialogSource).toMatch(/share\.saveShare/);
});
