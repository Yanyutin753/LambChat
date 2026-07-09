import { readFileSync } from "node:fs";
const approvalCss = readFileSync(
  new URL("../approval.css", import.meta.url),
  "utf8",
);
const askHumanSource = readFileSync(
  new URL(
    "../../components/chat/ChatMessage/items/AskHumanItem.tsx",
    import.meta.url,
  ),
  "utf8",
);

test("approval card uses shared section spacing for content blocks", () => {
  expect(approvalCss).toMatch(/--approval-section-x:\s*1\.25rem;/);
  expect(approvalCss).toMatch(/--approval-section-y:\s*0\.875rem;/);
  expect(approvalCss).toMatch(
    /\.approval-divider\s*\{[\s\S]*?margin:\s*0 var\(--approval-section-x\);/,
  );
  expect(approvalCss).toMatch(
    /\.approval-result-section\s*\{[\s\S]*?padding:\s*var\(--approval-section-y\) var\(--approval-section-x\);/,
  );
  expect(askHumanSource).not.toMatch(/className="px-5 pb-4"/);
  expect(askHumanSource).toMatch(/className="approval-result-section"/);
});
