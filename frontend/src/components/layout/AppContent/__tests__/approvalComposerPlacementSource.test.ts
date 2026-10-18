import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const chatViewSource = readFileSync(
  resolve(process.cwd(), "src/components/layout/AppContent/ChatView.tsx"),
  "utf8",
);
const approvalSource = readFileSync(
  resolve(process.cwd(), "src/components/panels/ApprovalPanel.tsx"),
  "utf8",
);
const approvalStyles = readFileSync(
  resolve(process.cwd(), "src/styles/approval.css"),
  "utf8",
);
const chatAppSource = readFileSync(
  resolve(process.cwd(), "src/components/layout/AppContent/ChatAppContent.tsx"),
  "utf8",
);
const approvalsHookSource = readFileSync(
  resolve(process.cwd(), "src/hooks/useApprovals.ts"),
  "utf8",
);

test("places approvals directly above the composer", () => {
  expect(chatViewSource).toMatch(
    /<ApprovalPanel[\s\S]*?<ChatInput[\s\S]*?showHelpMenu/,
  );
});

test("removes the fixed approval frame when there are no approvals", () => {
  expect(chatViewSource).toMatch(
    /\{hasPendingApproval \? \(\s*<div\s+className="approval-panel-scroll-region/,
  );
});

test("all approvals use the full ask-human card with visible actions", () => {
  expect(approvalSource).toMatch(
    /className="approval-card approval-card--composer approval-card--ask-human/,
  );
  expect(approvalSource).not.toMatch(
    /isExpanded|approval-compact|aria-expanded/,
  );
  expect(approvalSource).toMatch(
    /className="approval-actions approval-ask-human-footer font-serif"/,
  );
});

test("all pending approvals replace the composer", () => {
  expect(chatViewSource).toMatch(/hasPendingApproval = approvals\.length > 0/);
  expect(chatViewSource).toMatch(
    /\{hasPendingApproval \? \([\s\S]*?<ApprovalPanel[\s\S]*?\) : \(\s*<ChatInput/,
  );
});

test("pending approvals hide the goal bar and restore it with the composer", () => {
  expect(chatViewSource).not.toMatch(/<ActiveGoalBar\b/);
  expect(chatViewSource).toMatch(
    /\{hasPendingApproval \? \([\s\S]*?<ApprovalPanel[\s\S]*?\) : \(\s*<ChatInput[\s\S]*?activeGoal=\{composerGoal\}[\s\S]*?persistentGoal=\{persistentGoal\}/,
  );
});

test("pending approvals suppress welcome and loading composers without messages", () => {
  expect(chatViewSource).toMatch(
    /\{messages\.length === 0 \? \(\s*!hasPendingApproval &&\s*\(\s*isLoading \? \([\s\S]*?<ChatSkeleton[\s\S]*?<WelcomePage/,
  );
  expect(chatViewSource).toMatch(
    /\{\(messages\.length > 0 \|\| hasPendingApproval\) && \(\s*<div className="relative">/,
  );
});

test("approval composer follows the input column and rounded border", () => {
  expect(approvalSource).toMatch(
    /approval-scroll-container[^"\n]*overflow-visible[^"\n]*py-2[^"\n]*sm:py-3/,
  );
  expect(approvalSource).toMatch(
    /approval-panel-content-shell chat-content-column/,
  );
  expect(approvalStyles).toMatch(
    /\.approval-card\.approval-card--composer\s*\{[^}]*border-radius:\s*1rem;/s,
  );
});

test("confirmation cards inset slightly from the composer at each pane width", () => {
  expect(approvalStyles).toMatch(
    /\.approval-panel-content-shell\s*\{[^}]*box-sizing:\s*border-box;[^}]*padding-inline:\s*0\.75rem;/,
  );
  expect(approvalStyles).toMatch(
    /@container \(max-width: 40rem\)\s*\{\s*\.approval-panel-content-shell\s*\{\s*padding-inline:\s*0\.25rem;/,
  );
});

test("approval scrolling keeps the composer centered", () => {
  expect(approvalSource).toMatch(/approval-scroll-container/);
  expect(approvalStyles).toMatch(
    /\.approval-scroll-container\s*\{[^}]*overflow:\s*visible;/s,
  );
});

test("approval panel uses a maximum height without forcing a fixed frame", () => {
  const approvalRegion = approvalStyles.match(
    /\.approval-panel-scroll-region\s*\{[^}]*\}/s,
  )?.[0];

  expect(approvalRegion).toBeDefined();
  expect(approvalRegion).toMatch(/max-height:\s*31rem/);
  expect(approvalRegion).not.toMatch(/flex:\s*0\s+0\s+clamp/);
  expect(approvalRegion).not.toMatch(/height:\s*clamp/);
  expect(approvalStyles).not.toMatch(
    /\.approval-panel-scroll-region[\s\S]*?(?:flex-basis|height|min-height):\s*(?:min|clamp)\(/,
  );
  expect(chatViewSource).not.toMatch(
    /className="approval-panel-scroll-region[\s\S]*?style=\{\{[\s\S]*?height:/,
  );
});

test("approval composer lets short content determine its height", () => {
  expect(approvalStyles).toMatch(
    /\.approval-card\.approval-card--composer\.approval-card--ask-human\s*\{[^}]*flex:\s*0\s+1\s+auto;/s,
  );
  expect(approvalStyles).toMatch(
    /\.approval-card\.approval-card--composer\.approval-card--ask-human\s*>\s*div\[id\^="approval-details-"\]\s*\{[^}]*flex:\s*0\s+1\s+auto;/s,
  );
});

test("interrupt approvals never derive a visible deadline", () => {
  expect(approvalSource).toMatch(
    /a\.metadata\?\.mode === "interrupt"[\s\S]*continue/,
  );
});

test("forwards session-scoped approval clearing from useAgent", () => {
  expect(chatAppSource).toMatch(
    /onClearApprovals:\s*\(approvalSessionId\)\s*=>\s*\{\s*clearApprovals\(approvalSessionId\)/,
  );
});

test("forwards the server deadline and timeout into the confirmation card", () => {
  expect(chatAppSource).toMatch(
    /addApproval\(\{[^}]*expires_at: approval\.expires_at/,
  );
  expect(chatAppSource).toMatch(
    /addApproval\(\{[^}]*timeout: approval\.timeout/,
  );
});

test("passes the resumed run id to the stream recovery callback", () => {
  expect(chatAppSource).toMatch(
    /onInterruptResume:\s*\(runId, sourceSessionId\)\s*=>\s*ensureResumeStreamRef\.current\(runId, sourceSessionId\)/,
  );
  expect(chatAppSource).toMatch(
    /ensureResumeStreamRef\.current\s*=\s*\(runId, sourceSessionId\)\s*=>/,
  );
  expect(approvalsHookSource).toMatch(
    /onInterruptResume\?\.\(\s*res\.hitl_resume\.run_id,/,
  );
});
