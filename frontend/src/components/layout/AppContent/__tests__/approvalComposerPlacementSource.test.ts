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
    /\{approvals\.length > 0 && \(\s*<div\s+className="approval-panel-scroll-region/,
  );
});

test("approval panel exposes a collapsible Codex-style compact state", () => {
  expect(approvalSource).toMatch(/useState\(false\)/);
  expect(approvalSource).toMatch(/approval-compact/);
  expect(approvalSource).toMatch(/aria-expanded/);
});

test("approval composer matches the input width and rounded border", () => {
  expect(approvalSource).toMatch(
    /approval-scroll-container[^"\n]*overflow-visible[^"\n]*px-2[^"\n]*sm:px-8/,
  );
  expect(approvalSource).toMatch(
    /approval-panel-content-shell[^"]*mx-auto[^"]*w-full[^"]*max-w-4xl[^"]*lg:max-w-5xl[^"]*xl:max-w-6xl/,
  );
  expect(approvalStyles).toMatch(
    /\.approval-card\.approval-card--composer\s*\{[^}]*border-radius:\s*1\.5rem;/s,
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

test("passes the resumed run id to the stream recovery callback", () => {
  expect(chatAppSource).toMatch(
    /onInterruptResume:\s*\(runId\)\s*=>\s*ensureResumeStreamRef\.current\(runId\)/,
  );
  expect(chatAppSource).toMatch(
    /ensureResumeStreamRef\.current\s*=\s*\(runId\)\s*=>/,
  );
  expect(approvalsHookSource).toMatch(
    /onInterruptResume\?\.\(res\.hitl_resume\.run_id\)/,
  );
});
