import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const input = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const view = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);

test("the compact checklist remains outside the composer above approvals", () => {
  expect(input).not.toMatch(/todoSummary|SessionTodoDock/);
  expect(view).toMatch(
    /<SessionTodoDock[\s\S]*?<ApprovalPanel[\s\S]*?<ChatInput/,
  );
});
