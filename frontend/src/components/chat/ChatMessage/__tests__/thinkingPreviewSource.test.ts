import { readFileSync } from "node:fs";

test("ThinkingBlock displays the full smooth stream beside the stable title", () => {
  const source = readFileSync(
    new URL("../ThinkingBlock.tsx", import.meta.url),
    "utf8",
  );

  // Keep the live preview separate from the stable status title.
  expect(source).toContain(
    'const label = isStreaming ? t("chat.message.thinking") : settledLabel;',
  );
  expect(source).toContain("description={displayContent}");
});
