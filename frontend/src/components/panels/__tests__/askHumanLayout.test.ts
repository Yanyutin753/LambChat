import { readFileSync } from "node:fs";

const approvalSource = readFileSync(
  new URL("../ApprovalPanel.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);
const approvalCss = readFileSync(
  new URL("../../../styles/approval.css", import.meta.url),
  "utf8",
);

test("renders ask-human as a full card with numbered choices and footer actions", () => {
  expect(approvalSource).toMatch(/approval-card--ask-human/);
  expect(approvalSource).toMatch(/approval-ask-human-option/);
  expect(approvalSource).toMatch(/approvals\.ignore/);
  expect(approvalSource).toMatch(/approvals\.submit/);
});

test("places the ignore action before submit in the approval footer", () => {
  expect(approvalSource).toMatch(
    /approval-btn-cancel[\s\S]*?approval-btn-submit/,
  );
});

test("localizes ask-human labels and keeps one final submit action", () => {
  expect(approvalSource).toMatch(/approvals\.mainGoal/);
  expect(approvalSource).not.toMatch(/aria-label="上一项"/);
  expect(approvalSource).not.toMatch(/aria-label="下一项"/);
  expect(approvalSource).not.toMatch(
    /t\("approvals\.(?:mainGoal|continue|ignore)",\s*"/,
  );
  expect(approvalSource).toMatch(/t\("approvals\.submit"\)/);
  expect(approvalSource).not.toMatch(/t\("approvals\.continue"\)/);
});

test("localizes the backend-generated other-opinion field", () => {
  expect(approvalSource).toMatch(/field\.name === "_other"/);
  expect(approvalSource).toMatch(/chat\.message\.askHumanOtherLabel/);
  expect(approvalSource).toMatch(/chat\.message\.askHumanOtherPlaceholder/);
});

test("renders all ask-human fields in one form and validates them together", () => {
  expect(approvalSource).toMatch(/askHumanFields\.map/);
  expect(approvalSource).toMatch(
    /isAskHuman\s*&&\s*!isFormFieldsValid\(askHumanFields, currentFormValues\)/,
  );
  expect(approvalSource).not.toMatch(/askHumanFieldIndex/);
  expect(approvalSource).not.toMatch(/currentAskHumanField/);
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

test("keeps approval and chat input on the same responsive width contract", () => {
  expect(chatViewSource).toMatch(
    /approval-panel-scroll-region[\s\S]*?<ApprovalPanel/,
  );
  expect(approvalSource).toMatch(
    /approval-scroll-container h-full w-full min-h-0 overflow-visible px-2 py-2 sm:px-8 sm:py-3/,
  );
  expect(approvalSource).toMatch(
    /approval-panel-content-shell[^"]*mx-auto[^"]*w-full[^"]*max-w-4xl[^"]*lg:max-w-5xl[^"]*xl:max-w-6xl/,
  );
});

test("lets the ChatView parent own the bounded vertical scroll area", () => {
  expect(chatViewSource).toMatch(
    /className="approval-panel-scroll-region flex min-h-0 w-full shrink-0 flex-col overflow-hidden"/,
  );
  expect(approvalSource).toMatch(
    /approval-scroll-container[^"]*overflow-visible/,
  );
  expect(approvalCss).toMatch(
    /\.approval-panel-scroll-region\s*\{[\s\S]*?height:\s*auto;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-panel-scroll-region\s*\{[\s\S]*?max-height:\s*31rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-card\.approval-card--composer\s*\{[\s\S]*?max-height:\s*100%;/,
  );
});

test("keeps the approval frame visible while only its details scroll", () => {
  expect(approvalSource).toMatch(/approval-details-scroll/);
  expect(approvalSource).toMatch(/approval-panel-content-shell/);
  expect(approvalSource).toMatch(
    /approval-details-scroll[\s\S]*?approval-actions/,
  );
  expect(approvalCss).toMatch(
    /\.approval-card\.approval-card--composer[\s\S]*?display:\s*flex[\s\S]*?flex-direction:\s*column;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-details-scroll\s*\{[\s\S]*?overflow-y:\s*auto;/,
  );
});

test("keeps the ask-human card usable on narrow touch screens", () => {
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-title-row[\s\S]*?white-space:\s*nowrap;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-option[\s\S]*?min-height:\s*3rem;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-footer \.flex button span[\s\S]*?display:\s*inline;/,
  );
});

test("makes ask-human choices visibly interactive and selected", () => {
  expect(approvalSource).toMatch(/approval-ask-human-option-indicator/);
  expect(approvalSource).toMatch(/\{selected \? "✓" : index \+ 1\}/);
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option-indicator\s*\{[\s\S]*?border-radius:\s*999px;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:focus-visible[\s\S]*?outline:/,
  );
});

test("pins approval actions to the right with a clear button group", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-footer\s*\{[\s\S]*?justify-content:\s*flex-end;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-footer \.flex\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-btn-submit\s*\{[\s\S]*?min-height:\s*2\.5rem;/,
  );
});

test("uses a compact spacing rhythm for ask-human fields", () => {
  expect(approvalSource).toMatch(/approval-form--ask-human/);
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human\s*\{[\s\S]*?gap:\s*0\.75rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div \+ div[\s\S]*?padding-top:\s*0;/,
  );
});

test("aligns the ask-human title group on one vertically centered row", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-title-row\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?justify-content:\s*flex-start;[\s\S]*?white-space:\s*nowrap;/,
  );
});

test("keeps approval text readable without truncation", () => {
  expect(approvalSource).not.toMatch(/approval-summary block truncate/);
  expect(approvalCss).not.toMatch(/text-overflow:\s*ellipsis;/);
  expect(approvalCss).not.toMatch(
    /\.approval-ask-human-question\s*\{[^}]*white-space:\s*nowrap;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div > label[\s\S]*?font-size:\s*1rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human \.approval-input[\s\S]*?font-size:\s*1rem;/,
  );
});

test("uses a restrained card surface and consistent control rhythm", () => {
  expect(approvalCss).toMatch(
    /\.approval-card--ask-human\s*\{[\s\S]*?background:\s*var\(--approval-bg\);/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-header\s*\{[\s\S]*?border-bottom:\s*1px solid/,
  );
  expect(approvalCss).toMatch(
    /\.approval-input\s*\{[\s\S]*?min-height:\s*2\.75rem;/,
  );
});

test("aligns title, fields, choices, and actions to one horizontal inset", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-options\s*\{[\s\S]*?padding:\s*0;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-footer\s*\{[\s\S]*?padding:[\s\S]*?var\(--approval-section-x\)/,
  );
});

test("gives each ask-human option a visible vertical gap", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-options\s*\{[\s\S]*?row-gap:\s*0\.5rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-options\s*\{[\s\S]*?column-gap:\s*0;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-options[\s\S]*?row-gap:\s*0\.4rem;/,
  );
});

test("aligns ask-human options to the same content start as labels and inputs", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-options\s*\{[\s\S]*?padding:\s*0;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option\s*\{[\s\S]*?display:\s*grid;[\s\S]*?grid-template-columns:\s*1\.65rem minmax\(0, 1fr\);/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option\s*\{[\s\S]*?font-size:\s*1rem;[\s\S]*?line-height:\s*1\.5;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-options[\s\S]*?padding:\s*0\.1rem 0 0\.25rem;/,
  );
});

test("uses the same readable body line-height for question and options", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-question\s*\{[^}]*?font-size:\s*1rem;[^}]*?line-height:\s*1\.5;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option\s*\{[^}]*?font-size:\s*1rem;[^}]*?line-height:\s*1\.5;/,
  );
});

test("keeps hover, keyboard focus, and selected states visually distinct", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:hover:not\(\.approval-ask-human-option--selected\)/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option--focused:not\(\.approval-ask-human-option--selected\)[\s\S]*?box-shadow:/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option--selected\s*\{[^}]*?box-shadow:[\s\S]*?0 3px 12px -9px/,
  );
  expect(approvalCss).not.toMatch(
    /\.approval-ask-human-option--selected\s*\{[^}]*?inset/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:focus-visible\s*\{[^}]*?outline:\s*2px/,
  );
});

test("keeps the ask-human shortcut hint readable beside the actions", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-shortcut-hint\s*\{[^}]*?font-size:\s*0\.875rem;[^}]*?line-height:\s*1\.5;/,
  );
});

test("announces multi-select choices with an accessible reminder", () => {
  expect(approvalSource).toMatch(/aria-multiselectable=\{isMultiple\}/);
  expect(approvalSource).toMatch(/approval-ask-human-choice-field/);
  expect(approvalSource).toMatch(/approval-ask-human-multi-select-hint/);
  expect(approvalSource).toMatch(/approvals\.multiSelectHint/);
  expect(approvalCss).toMatch(
    /\.approval-ask-human-multi-select-hint\s*\{[^}]*?font-size:\s*0\.8125rem;[^}]*?line-height:\s*1\.4;/,
  );
});

test("keeps the multi-select reminder visually secondary", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-multi-select-hint\s*\{[^}]*?font-size:\s*0\.8125rem;[^}]*?opacity:\s*0\.82;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-multi-select-hint::before\s*\{[^}]*?background:\s*var\(--approval-text-dim\);[^}]*?box-shadow:\s*none;/,
  );
});

test("uses one vertical rhythm across ask-human fields", () => {
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human\s*\{[^}]*?gap:\s*0\.75rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div\s*\{[^}]*?display:\s*flex;[^}]*?gap:\s*0\.45rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div\.space-y-1 > \* \+ \*\s*\{[^}]*?margin-top:\s*0;/,
  );
});

test("keeps selected and hover accents restrained", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:hover:not\(\.approval-ask-human-option--selected\)[\s\S]*?background:[\s\S]*?12%/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option--selected\s*\{[\s\S]*?background:[\s\S]*?18%/,
  );
});

test("keeps the approval card surfaces visually quiet", () => {
  expect(approvalCss).toMatch(
    /\.approval-card\.approval-card--composer\s*\{[\s\S]*?var\(--approval-accent\) 24%/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-header\s*\{[\s\S]*?var\(--approval-border\) 45%/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-footer\s*\{[\s\S]*?var\(--approval-border\) 55%/,
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
