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

test("keeps space between the final operation list and the footer divider", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-context:last-child\s*\{[^}]*padding-bottom:\s*var\(--approval-section-y\);/,
  );
});

test("uses the same vertical inset for approval header, fields, and actions", () => {
  for (const selector of ["approval-ask-human-header", "approval-actions"]) {
    expect(approvalCss).toMatch(
      new RegExp(
        `\\.${selector}\\s*\\{[^}]*padding:\\s*var\\(--approval-section-y\\) var\\(--approval-section-x\\);`,
      ),
    );
  }
  expect(approvalCss).not.toMatch(
    /\.approval-form--ask-human\s*\{[^}]*padding-(?:top|bottom):/,
  );
});

test("keeps operation labels above commands at every container width", () => {
  expect(approvalCss).toMatch(
    /\.approval-op-row\s*\{[^}]*display:\s*grid;[^}]*grid-template-columns:\s*max-content minmax\(0, 1fr\);/,
  );
  for (const name of ["verb", "detail"]) {
    expect(approvalCss).toMatch(
      new RegExp(
        `\\.approval-op-${name}\\s*\\{[^}]*grid-column:\\s*2;[^}]*min-width:\\s*0;`,
      ),
    );
  }
  expect(approvalCss).not.toMatch(/\.approval-op-verb\s*\{[^}]*border-radius/);
  expect(approvalCss.match(/^\.approval-op-row\s*\{/gm)).toHaveLength(1);
});

test("renders sandbox-confirm batches as a structured op list, not one crammed line", () => {
  // 沙箱确认门的 message 是「标题 + 编号操作」多行文本：头部只放标题行，
  // 明细区渲染单据式操作清单，命令走等宽字体 + 任意断行
  expect(approvalSource).toMatch(
    /parseAskHumanMessage\(currentApproval\.message\)/,
  );
  expect(approvalSource).toMatch(
    /askHumanQuestion = askHumanParsed\.headline \?\? approvalSummary/,
  );
  expect(approvalSource).toMatch(/ApprovalOpList ops=\{askHumanParsed\.ops\}/);
  expect(approvalSource).toMatch(/approval-ask-human-context/);
  expect(approvalSource).toMatch(/askHumanParsed\.prose/);
  expect(approvalCss).toMatch(
    /\.approval-op-list\s*\{[\s\S]*?flex-direction:\s*column;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-op-detail\s*\{[\s\S]*?overflow-wrap:\s*anywhere;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-op-row \+ \.approval-op-row\s*\{[\s\S]*?border-top:\s*1px solid/,
  );
});

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
  // 「主要目标」徽标与问题语义无关，头部只渲染问题本身
  expect(approvalSource).not.toMatch(/approvals\.mainGoal/);
  expect(approvalSource).not.toMatch(/approval-ask-human-badge/);
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
  expect(approvalSource).toMatch(/askHumanDisplayFields\.map/);
  expect(approvalSource).toMatch(
    /isLoading \|\| !isFormFieldsValid\(currentApproval\.fields, currentFormValues\)/,
  );
  expect(approvalSource).not.toMatch(/askHumanFieldIndex/);
  expect(approvalSource).not.toMatch(/currentAskHumanField/);
});

test("hides the composer while an approval is pending", () => {
  expect(chatViewSource).toMatch(
    /hasPendingApproval \? \([\s\S]*?<ApprovalPanel[\s\S]*?\) : \(\s*<ChatInput/,
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
    /approval-scroll-container h-full w-full min-h-0 overflow-visible py-2 sm:py-3/,
  );
  expect(approvalSource).toMatch(
    /approval-panel-content-shell chat-content-column/,
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
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-title-row[\s\S]*?white-space:\s*normal;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-option[\s\S]*?min-height:\s*3rem;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-footer > \.flex button > span:last-child[\s\S]*?display:\s*inline;/,
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
    /\.approval-ask-human-footer > \.flex\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-btn-submit\s*\{[\s\S]*?min-height:\s*2\.5rem;/,
  );
});

test("uses a compact spacing rhythm for ask-human fields", () => {
  expect(approvalSource).toMatch(/approval-form--ask-human/);
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human\s*\{[\s\S]*?gap:\s*1rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div \+ div[\s\S]*?padding-top:\s*0;/,
  );
});

test("centers the title group and lets long confirmation questions wrap", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-title-row\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?justify-content:\s*flex-start;[\s\S]*?white-space:\s*normal;/,
  );
});

test("keeps approval text readable without truncation", () => {
  expect(approvalSource).not.toMatch(/approval-summary block truncate/);
  expect(approvalCss).not.toMatch(
    /\.approval-ask-human-question\s*\{[^}]*white-space:\s*nowrap;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div > label[\s\S]*?font-size:\s*0\.8125rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human \.approval-input[\s\S]*?font-size:\s*0\.8125rem;/,
  );
});

test("renders ask-human questions bold for clearer scanning", () => {
  // 问题标签加粗，与选项内容拉开层级
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div > label[\s\S]*?font-weight:\s*600;/,
  );
});

test("shows confirmation details without a collapsed raw-text summary", () => {
  expect(approvalSource).not.toMatch(/isExpanded|approval-summary/);
  expect(approvalCss).not.toMatch(/\.approval-summary\s*\{/);
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
    /\.approval-ask-human-option\s*\{[\s\S]*?font-size:\s*0\.8125rem;[\s\S]*?line-height:\s*1\.5;/,
  );
  expect(approvalCss).toMatch(
    /@media \(max-width: 640px\)[\s\S]*?\.approval-ask-human-options[\s\S]*?padding:\s*0\.1rem 0 0\.25rem;/,
  );
});

test("keeps ask-human form text one step smaller than the question", () => {
  // 表单区（标签/选项/输入框）比头部问题再小一档，行高保持一致的可读节奏
  expect(approvalCss).toMatch(
    /\.approval-ask-human-question\s*\{[^}]*?font-size:\s*0\.875rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option\s*\{[^}]*?font-size:\s*0\.8125rem;[^}]*?line-height:\s*1\.5;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option\s*\{[^}]*?min-height:\s*2\.5rem;/,
  );
});

test("keeps hover, keyboard focus, and selected states visually distinct", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:hover:not\(\.approval-ask-human-option--selected\)/,
  );
  // 自定义键盘光标高亮已整体移除，只剩原生 :focus-visible 焦点可访问性
  expect(approvalCss).not.toMatch(/approval-ask-human-option--focused/);
  // 选中态靠边框+浅底+加粗区分，不靠投影光晕
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option--selected\s*\{[^}]*?font-weight:\s*500;/,
  );
  expect(approvalCss).not.toMatch(
    /\.approval-ask-human-option--selected\s*\{[^}]*?box-shadow/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:focus-visible\s*\{[^}]*?outline:\s*2px/,
  );
});

test("keeps the ask-human shortcut hint readable beside the actions", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-shortcut-hint\s*\{[^}]*?font-size:\s*0\.8125rem;[^}]*?line-height:\s*1\.5;/,
  );
});

test("announces multi-select choices with an accessible reminder", () => {
  expect(approvalSource).toMatch(/aria-multiselectable=\{isMultiple\}/);
  expect(approvalSource).toMatch(/approval-ask-human-choice-field/);
  expect(approvalSource).toMatch(/approval-ask-human-multi-select-hint/);
  expect(approvalSource).toMatch(/approvals\.multiSelectHint/);
  expect(approvalCss).toMatch(
    /\.approval-ask-human-multi-select-hint\s*\{[^}]*?font-size:\s*0\.6875rem;[^}]*?line-height:\s*1\.4;/,
  );
});

test("keeps the multi-select reminder visually secondary", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-multi-select-hint\s*\{[^}]*?font-size:\s*0\.6875rem;[^}]*?opacity:\s*0\.82;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-multi-select-hint::before\s*\{[^}]*?background:\s*var\(--approval-text-dim\);[^}]*?box-shadow:\s*none;/,
  );
});

test("uses one vertical rhythm across ask-human fields", () => {
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human\s*\{[^}]*?gap:\s*1rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div\s*\{[^}]*?display:\s*flex;[^}]*?gap:\s*0\.6rem;/,
  );
  expect(approvalCss).toMatch(
    /\.approval-form--ask-human > div\.space-y-1 > \* \+ \*\s*\{[^}]*?margin-top:\s*0;/,
  );
});

test("keeps selected and hover accents restrained", () => {
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option:hover:not\(\.approval-ask-human-option--selected\)[\s\S]*?background:[\s\S]*?8%/,
  );
  expect(approvalCss).toMatch(
    /\.approval-ask-human-option--selected\s*\{[\s\S]*?background:[\s\S]*?14%/,
  );
});

test("only mouse clicks toggle single-select choices", () => {
  // toggle 只存在于鼠标点击路径（再点取消）；键盘层已移除，不存在快捷键误取消
  expect(
    (approvalSource.match(/toggleSingleSelectValue\(/g) ?? []).length,
  ).toBe(1);
});

test("keeps the approval card surfaces visually quiet", () => {
  expect(approvalCss).toMatch(
    /\.approval-card\.approval-card--composer\s*\{[^}]*border-color:\s*var\(--approval-border\);[^}]*box-shadow:\s*none;/,
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

test("skips the enter shortcut while typing inside card text controls", () => {
  expect(approvalSource).toMatch(
    /isEditableEventTarget\(event\.target\)[\s\S]*?event\.key !== "Enter"/,
  );
});

test("lets a single-select choice be deselected by clicking it again", () => {
  // 单选再点同一项应取消选择（toggle），而不是只能换选
  expect(approvalSource).toMatch(/toggleSingleSelectValue\(/);
});

test("ask-human options carry no custom keyboard cursor highlight", () => {
  // 数字键/↑↓/光标高亮整套自定义键盘层已移除：不再有任何"乱 hover"高亮源
  expect(approvalSource).not.toMatch(/askHumanSelectedIndex/);
  expect(approvalSource).not.toMatch(/approval-ask-human-option--focused/);
  expect(approvalCss).not.toMatch(/approval-ask-human-option--focused/);
});

test("enter submits the ask-human answer from anywhere on the card", () => {
  // 唯一保留的快捷键：Enter 提交（文本框内换行、按钮上原生激活除外）
  expect(approvalSource).toMatch(/event\.key !== "Enter"/);
  expect(approvalSource).toMatch(/handleSubmit\(\);/);
});
