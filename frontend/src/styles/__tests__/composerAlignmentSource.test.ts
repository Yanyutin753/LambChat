import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("composer labels share a fixed line box and icons share a 16px box", () => {
  const chip = read("../../components/chat/ToolbarChip.tsx");
  const toolbar = read("../../components/chat/ChatInputToolbar.tsx");
  const usage = read("../../components/chat/ComposerUsageChip.tsx");
  expect(chip).toContain("h-4 w-4");
  expect(chip).toContain("text-14 leading-5");
  expect(usage).toContain("text-14 leading-5");
  expect(toolbar).not.toMatch(/size=\{18\}|\[18px\]/);
  expect(read("../chat.css")).toMatch(
    /\.chat-input-toolbar\s+\.chat-tool-btn\s+svg\s*\{[^}]*flex-shrink:\s*0/s,
  );
});
