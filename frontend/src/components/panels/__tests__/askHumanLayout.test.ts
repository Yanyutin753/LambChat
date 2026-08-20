import { readFileSync } from "node:fs";

const approvalSource = readFileSync(
  new URL("../ApprovalPanel.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);

test("renders ask-human as a full card with numbered choices and footer actions", () => {
  expect(approvalSource).toMatch(/approval-card--ask-human/);
  expect(approvalSource).toMatch(/approval-ask-human-option/);
  expect(approvalSource).toMatch(/approvals\.ignore/);
  expect(approvalSource).toMatch(/approvals\.continue/);
});

test("paginates ask-human fields one question at a time", () => {
  expect(approvalSource).toMatch(/askHumanFieldIndex/);
  expect(approvalSource).toMatch(/currentAskHumanField/);
  expect(approvalSource).toMatch(
    /isAskHuman[\s\S]*?currentAskHumanField\.label/,
  );
});

test("hides the composer while an approval is pending", () => {
  expect(chatViewSource).toMatch(
    /!hasPendingAskHumanApproval\s*&&\s*\([\s\S]*?<ChatInput/,
  );
});

test("keeps approval scrolling on the ChatView parent region", () => {
  expect(chatViewSource).toMatch(/chat-view-content-region/);
  expect(chatViewSource).toMatch(
    /approval-panel-scroll-region[\s\S]*?<ApprovalPanel/,
  );
  expect(approvalSource).toMatch(
    /approval-scroll-container[^"]*overflow-visible/,
  );
});
