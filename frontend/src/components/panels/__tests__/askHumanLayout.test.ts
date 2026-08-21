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

test("localizes ask-human labels and pagination controls", () => {
  expect(approvalSource).toMatch(/approvals\.mainGoal/);
  expect(approvalSource).toMatch(/approvals\.previous/);
  expect(approvalSource).toMatch(/approvals\.next/);
  expect(approvalSource).toMatch(/aria-label=\{t\("approvals\.previous"\)\}/);
  expect(approvalSource).toMatch(/aria-label=\{t\("approvals\.next"\)\}/);
  expect(approvalSource).not.toMatch(/aria-label="上一项"/);
  expect(approvalSource).not.toMatch(/aria-label="下一项"/);
  expect(approvalSource).not.toMatch(
    /t\("approvals\.(?:mainGoal|continue|ignore)",\s*"/,
  );
});

test("localizes the backend-generated other-opinion field", () => {
  expect(approvalSource).toMatch(/currentAskHumanField\.name === "_other"/);
  expect(approvalSource).toMatch(/chat\.message\.askHumanOtherLabel/);
  expect(approvalSource).toMatch(/chat\.message\.askHumanOtherPlaceholder/);
});

test("paginates ask-human fields one question at a time", () => {
  expect(approvalSource).toMatch(/askHumanFieldIndex/);
  expect(approvalSource).toMatch(/currentAskHumanField/);
  expect(approvalSource).toMatch(
    /isAskHuman[\s\S]*?currentAskHumanDisplayField\.label/,
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

test("shows desktop-only keyboard shortcut hint for ask-human choices", () => {
  // 快捷键提示仅在桌面端显示（手机端无键盘，隐藏提示文字）
  expect(approvalSource).toMatch(/approvals\.shortcutHint/);
  expect(approvalSource).toMatch(/approval-ask-human-shortcut-hint/);
  expect(approvalSource).toMatch(/hidden sm:inline-flex/);
});

test("supports number-key selection for ask-human choices", () => {
  expect(approvalSource).toMatch(/event\.key >= "1"/);
});
