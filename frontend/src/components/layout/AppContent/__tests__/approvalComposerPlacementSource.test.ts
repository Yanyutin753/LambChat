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

test("places approvals directly above the composer", () => {
  expect(chatViewSource).toMatch(
    /<ApprovalPanel[\s\S]*?<ChatInput[\s\S]*?showHelpMenu/,
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
    /mx-auto w-full max-w-4xl lg:max-w-5xl xl:max-w-6xl\"/,
  );
  expect(approvalStyles).toMatch(
    /\.approval-card\.approval-card--composer\s*\{[^}]*border-radius:\s*1\.5rem;/s,
  );
});

test("approval scrolling keeps the composer centered", () => {
  expect(approvalSource).toMatch(/approval-scroll-container/);
  expect(approvalStyles).toMatch(
    /\.approval-scroll-container\s*\{[^}]*scrollbar-gutter:\s*stable both-edges;/s,
  );
});

test("interrupt approvals never derive a visible deadline", () => {
  expect(approvalSource).toMatch(
    /a\.metadata\?\.mode === "interrupt"[\s\S]*continue/,
  );
});
