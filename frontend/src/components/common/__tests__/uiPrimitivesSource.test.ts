import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function assertExports(source: string, name: string): void {
  assert.match(
    source,
    new RegExp(`export \\{[\\s\\S]*\\b${name}\\b[\\s\\S]*\\} from`),
  );
}

function assertCssSelector(source: string, selector: string): void {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  assert.match(source, new RegExp(`${escaped}[\\s\\S]*?\\{`));
}

function cssBlock(source: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  assert.ok(match, `Expected CSS block for ${selector}`);
  return match[1];
}

test("common ui primitives are exposed from a single reusable entrypoint", () => {
  const commonIndex = readSource("../index.ts");
  const uiIndex = readSource("../ui/index.ts");

  for (const name of [
    "Button",
    "IconButton",
    "Input",
    "Textarea",
    "Select",
    "PickerTrigger",
    "FormField",
  ]) {
    assertExports(uiIndex, name);
    assertExports(commonIndex, name);
  }

  assert.match(uiIndex, /export type \{ ButtonVariant, ButtonSize \}/);
  assert.match(uiIndex, /export type \{ SelectOption \}/);
});

test("common panel controls are exposed for consistent admin panel composition", () => {
  const commonIndex = readSource("../index.ts");
  const panelControls = readSource("../PanelControls.tsx");

  for (const name of ["PanelFilterSelect", "PanelFooterActions"]) {
    assertExports(commonIndex, name);
  }

  assert.match(panelControls, /import \{ Select \}/);
  assert.match(panelControls, /panel-filter-select/);
  assert.match(panelControls, /panel-footer-actions/);
});

test("toolbar icon button centralizes shared panel toolbar button behavior", () => {
  const commonIndex = readSource("../index.ts");
  const uiIndex = readSource("../ui/index.ts");
  const toolbarIconButton = readSource("../ui/ToolbarIconButton.tsx");
  const documentToolbar = readSource(
    "../../documents/DocumentPreviewToolbar.tsx",
  );
  const toolResultPanel = readSource(
    "../../chat/ChatMessage/items/ToolResultPanel.tsx",
  );

  assertExports(uiIndex, "ToolbarIconButton");
  assertExports(commonIndex, "ToolbarIconButton");
  assert.match(
    toolbarIconButton,
    /type ToolbarIconButtonVariant = "stone" \| "muted"/,
  );
  assert.match(toolbarIconButton, /stopPropagation\(\)/);
  assert.match(toolbarIconButton, /flex shrink-0 items-center justify-center/);
  assert.match(toolbarIconButton, /size-8 rounded-lg/);
  assert.match(toolbarIconButton, /size-8 rounded-xl/);

  assert.match(documentToolbar, /import \{[\s\S]*ToolbarIconButton/);
  assert.match(toolResultPanel, /import \{[\s\S]*ToolbarIconButton/);
  assert.doesNotMatch(documentToolbar, /const toolbarBtnClass/);
  assert.doesNotMatch(toolResultPanel, /const panelBtnClass/);
  assert.doesNotMatch(toolResultPanel, /const panelCloseBtnClass/);
});

test("floating icon button centralizes fullscreen overlay icon actions", () => {
  const commonIndex = readSource("../index.ts");
  const uiIndex = readSource("../ui/index.ts");
  const floatingIconButton = readSource("../ui/FloatingIconButton.tsx");
  const documentToolbar = readSource(
    "../../documents/DocumentPreviewToolbar.tsx",
  );
  const skillFullscreen = readSource("../../skill/SkillFormFullscreen.tsx");

  assertExports(uiIndex, "FloatingIconButton");
  assertExports(commonIndex, "FloatingIconButton");
  assert.match(floatingIconButton, /fixed right-4 z-\[410\]/);
  assert.match(floatingIconButton, /flex shrink-0 items-center justify-center/);
  assert.match(floatingIconButton, /w-11 h-11 rounded-xl bg-black\/80/);

  assert.match(documentToolbar, /import \{[\s\S]*FloatingIconButton/);
  assert.match(skillFullscreen, /import \{ FloatingIconButton \}/);
  assert.doesNotMatch(documentToolbar, /w-11 h-11 rounded-xl bg-black\/80/);
  assert.doesNotMatch(skillFullscreen, /w-11 h-11 rounded-xl bg-black\/80/);
});

test("viewer toolbar uses a fixed-size reusable icon button for overlay controls", () => {
  const source = readSource("../ViewerToolbar.tsx");

  assert.match(source, /function ViewerToolbarButton/);
  assert.match(source, /flex shrink-0 items-center justify-center size-8/);
  assert.match(source, /disabled:opacity-50 disabled:cursor-not-allowed/);
  assert.match(source, /<ViewerToolbarButton[\s\S]*imageViewer\.rotateLeft/);
  assert.match(source, /<ViewerToolbarButton[\s\S]*imageViewer\.zoomOut/);
  assert.match(source, /<ViewerToolbarButton[\s\S]*imageViewer\.reset/);
  assert.doesNotMatch(
    source,
    /<button[\s\S]*flex items-center justify-center size-8 rounded-lg hover:bg-white\/10/,
  );
});

test("viewer top bar buttons keep overlay actions fixed and non-wrapping", () => {
  const commonIndex = readSource("../index.ts");
  const topBar = readSource("../ViewerTopBar.tsx");
  const source = readSource("../ViewerTopBarButton.tsx");
  const imageViewer = readSource("../ImageViewer.tsx");
  const videoViewer = readSource("../VideoViewer.tsx");
  const mermaidViewer = readSource("../../chat/ChatMessage/MermaidDiagram.tsx");
  const excalidrawViewer = readSource(
    "../../documents/previews/ExcalidrawPreview.tsx",
  );

  assertExports(commonIndex, "ViewerTopBar");
  assert.match(topBar, /safe-area-top bg-black/);
  assert.match(topBar, /flex h-16 items-center justify-between px-3 sm:px-6/);
  assertExports(commonIndex, "ViewerTopBarButton");
  assert.match(source, /flex shrink-0/);
  assert.match(source, /whitespace-nowrap/);
  assert.match(source, /w-10 h-10/);
  assert.match(source, /px-3 h-10/);
  assert.match(source, /disabled:opacity-50 disabled:cursor-not-allowed/);

  assert.match(imageViewer, /import \{ ViewerTopBarButton \}/);
  assert.match(videoViewer, /import \{ ViewerTopBarButton \}/);
  assert.match(imageViewer, /import \{ ViewerTopBar \}/);
  assert.match(videoViewer, /import \{ ViewerTopBar \}/);
  assert.match(mermaidViewer, /import \{[\s\S]*ViewerTopBar/);
  assert.match(excalidrawViewer, /import \{[\s\S]*ViewerTopBar/);
  assert.match(imageViewer, /<ViewerTopBarButton[\s\S]*common\.close/);
  assert.match(videoViewer, /<ViewerTopBarButton[\s\S]*common\.close/);
  assert.match(mermaidViewer, /import \{[\s\S]*ViewerTopBarButton/);
  assert.match(excalidrawViewer, /import \{[\s\S]*ViewerTopBarButton/);
  assert.match(mermaidViewer, /<ViewerTopBarButton[\s\S]*common\.close/);
  assert.match(
    mermaidViewer,
    /<ViewerTopBarButton[\s\S]*imageViewer\.download/,
  );
  assert.match(excalidrawViewer, /<ViewerTopBarButton[\s\S]*common\.close/);
  assert.match(
    excalidrawViewer,
    /<ViewerTopBarButton[\s\S]*documents\.download/,
  );
  assert.doesNotMatch(
    [imageViewer, videoViewer, mermaidViewer, excalidrawViewer].join("\n"),
    /className=\{?btnCls\}?|className="flex items-center (?:justify-center w-10 h-10|gap-1\.5 rounded-lg px-3 h-10[^"]*text-white\/70)/,
  );
});

test("image and video viewers share direct URL download behavior", () => {
  const commonIndex = readSource("../index.ts");
  const helper = readSource("../viewerDownload.ts");
  const imageViewer = readSource("../ImageViewer.tsx");
  const videoViewer = readSource("../VideoViewer.tsx");

  assertExports(commonIndex, "downloadUrl");
  assert.match(helper, /export function downloadUrl/);
  assert.match(helper, /document\.createElement\("a"\)/);
  assert.match(helper, /anchor\.download = fileName \?\? ""/);
  assert.match(helper, /anchor\.click\(\)/);

  assert.match(imageViewer, /import \{ downloadUrl \}/);
  assert.match(videoViewer, /import \{ downloadUrl \}/);
  assert.match(imageViewer, /onClick=\{\(\) => downloadUrl\(src\)\}/);
  assert.match(videoViewer, /onClick=\{\(\) => downloadUrl\(src\)\}/);
  assert.doesNotMatch(
    [imageViewer, videoViewer].join("\n"),
    /document\.createElement\("a"\)|\.download = ""/,
  );
});

test("diagram viewers share blob download behavior", () => {
  const commonIndex = readSource("../index.ts");
  const helper = readSource("../viewerDownload.ts");
  const menuItem = readSource("../ViewerDropdownMenuItem.tsx");
  const mermaidViewer = readSource("../../chat/ChatMessage/MermaidDiagram.tsx");
  const documentMermaidViewer = readSource(
    "../../documents/previews/MermaidDiagram.tsx",
  );
  const excalidrawViewer = readSource(
    "../../documents/previews/ExcalidrawPreview.tsx",
  );

  assertExports(commonIndex, "downloadBlob");
  assert.match(helper, /export function downloadBlob/);
  assert.match(helper, /URL\.createObjectURL\(blob\)/);
  assert.match(helper, /downloadUrl\(url, fileName\)/);
  assert.match(helper, /URL\.revokeObjectURL\(url\)/);
  assertExports(commonIndex, "ViewerDropdownMenuItem");
  assert.match(
    menuItem,
    /type ViewerDropdownMenuItemVariant = "stone" \| "dark"/,
  );
  assert.match(menuItem, /whitespace-nowrap/);

  assert.match(mermaidViewer, /import \{ downloadBlob \}/);
  assert.match(mermaidViewer, /import \{[\s\S]*ViewerDropdownMenuItem/);
  assert.match(documentMermaidViewer, /import \{ downloadBlob \}/);
  assert.match(documentMermaidViewer, /import \{[\s\S]*ViewerDropdownMenuItem/);
  assert.match(excalidrawViewer, /import \{ downloadBlob \}/);
  assert.match(excalidrawViewer, /import \{[\s\S]*ViewerDropdownMenuItem/);
  assert.match(mermaidViewer, /downloadBlob\([^)]*"diagram\.svg"/);
  assert.match(mermaidViewer, /downloadBlob\([^)]*"diagram\.png"/);
  assert.match(mermaidViewer, /downloadBlob\([^)]*"mermaid\.svg"/);
  assert.match(mermaidViewer, /<ViewerDropdownMenuItem[\s\S]*SVG/);
  assert.match(mermaidViewer, /<ViewerDropdownMenuItem[\s\S]*PNG/);
  assert.match(documentMermaidViewer, /downloadBlob\([^)]*"diagram\.svg"/);
  assert.match(documentMermaidViewer, /downloadBlob\([^)]*"diagram\.png"/);
  assert.match(documentMermaidViewer, /<ViewerDropdownMenuItem[\s\S]*SVG/);
  assert.match(documentMermaidViewer, /<ViewerDropdownMenuItem[\s\S]*PNG/);
  assert.match(
    excalidrawViewer,
    /downloadBlob\([^)]*"excalidraw-diagram\.svg"/,
  );
  assert.match(
    excalidrawViewer,
    /downloadBlob\([^)]*"excalidraw-diagram\.png"/,
  );
  assert.match(
    excalidrawViewer,
    /<ViewerDropdownMenuItem[\s\S]*variant="dark"[\s\S]*SVG/,
  );
  assert.match(
    excalidrawViewer,
    /<ViewerDropdownMenuItem[\s\S]*variant="dark"[\s\S]*PNG/,
  );
  assert.doesNotMatch(
    [mermaidViewer, documentMermaidViewer, excalidrawViewer].join("\n"),
    /const (?:pngUrl|url) = URL\.createObjectURL\(blob\)|URL\.revokeObjectURL\(pngUrl\)|w-full px-(?:3 py-2 text-left text-xs text-stone-700|4 py-2\.5 text-left text-sm text-white\/80)/,
  );
});

test("overlay round icon button centralizes center-mode floating panel actions", () => {
  const commonIndex = readSource("../index.ts");
  const uiIndex = readSource("../ui/index.ts");
  const source = readSource("../ui/OverlayRoundIconButton.tsx");
  const toolResultPanel = readSource(
    "../../chat/ChatMessage/items/ToolResultPanel.tsx",
  );

  assertExports(uiIndex, "OverlayRoundIconButton");
  assertExports(commonIndex, "OverlayRoundIconButton");
  assert.match(source, /flex shrink-0 items-center justify-center/);
  assert.match(source, /w-10 h-10 rounded-full bg-black\/70/);
  assert.match(source, /hover:bg-black\/90 text-white shadow-lg/);

  assert.match(toolResultPanel, /import \{[\s\S]*OverlayRoundIconButton/);
  assert.match(toolResultPanel, /<OverlayRoundIconButton[\s\S]*common\.back/);
  assert.match(toolResultPanel, /<OverlayRoundIconButton[\s\S]*common\.close/);
  assert.doesNotMatch(toolResultPanel, /rounded-full bg-black\/70/);
});

test("ui primitive styles share one visual system in components css", () => {
  const css = readSource("../../../styles/components.css");

  for (const selector of [
    ".ui-button",
    ".ui-button--primary",
    ".ui-button--secondary",
    ".ui-button--ghost",
    ".ui-button--danger",
    ".ui-icon-button",
    ".ui-field",
    ".ui-input",
    ".ui-textarea",
    ".ui-select-trigger",
    ".ui-select-dropdown",
    ".ui-select-option",
    ".ui-picker-trigger",
  ]) {
    assertCssSelector(css, selector);
  }

  assert.match(css, /\.btn-primary\s*\{[\s\S]*?\.ui-button--primary/);
  assert.match(css, /\.glass-input\.es-input\s*\{[\s\S]*?\.ui-input/);

  const buttonLabel = cssBlock(css, ".ui-button__label");
  assert.match(buttonLabel, /display:\s*inline-flex/);
  assert.match(buttonLabel, /white-space:\s*nowrap/);
});

test("legacy GlassSelect delegates to the shared Select primitive", () => {
  const source = readSource("../GlassSelect.tsx");

  assert.match(source, /import \{ Select \}/);
  assert.match(source, /return \([\s\S]*<Select/);
  assert.match(
    source,
    /placeholder=\{placeholder \?\? options\[0\]\?\.label \?\? ""\}/,
  );
});

test("first migrated admin forms consume shared primitives instead of generic legacy classes", () => {
  const migratedSources = [
    readSource("../../panels/SkillsPanel/GithubImportModal.tsx"),
    readSource("../../panels/SkillsPanel/ZipUploadModal.tsx"),
    readSource("../../panels/SkillsPanel/PublishDialog.tsx"),
    readSource("../../mcp/MCPServerForm.tsx"),
  ].join("\n");

  assert.match(migratedSources, /import \{ Button/);
  assert.match(
    migratedSources,
    /import \{ Button, FormField, Input, Textarea \}/,
  );
  assert.match(migratedSources, /<Button[\s>]/);
  assert.match(migratedSources, /<Input[\s>]/);
  assert.match(migratedSources, /<Textarea[\s>]/);
  assert.match(migratedSources, /<FormField[\s>]/);
  assert.doesNotMatch(
    migratedSources,
    /className="btn-(primary|secondary)[^"]*"/,
  );
  assert.doesNotMatch(migratedSources, /className="input-field[^"]*"/);
});

test("mcp server form uses shared icon buttons for generic icon actions", () => {
  const source = readSource("../../mcp/MCPServerForm.tsx");

  assert.match(source, /import \{ Button, IconButton, Input, Select \}/);
  assert.match(source, /<Select[\s\S]*availableTransports/);
  assert.match(source, /<Input[\s\S]*mcp\.form\.serverNamePlaceholder/);
  assert.match(source, /<IconButton[\s\S]*removeHeader/);
  assert.doesNotMatch(source, /className="btn-icon[^"]*"/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /className="glass-input/);
});

test("custom admin pickers reuse shared picker trigger and input primitives", () => {
  const providerSelect = readSource(
    "../../panels/AgentPanel/shared/ProviderSelect.tsx",
  );
  const modelIconSelect = readSource(
    "../../panels/ModelPanel/tabs/ModelIconSelect.tsx",
  );
  const source = [providerSelect, modelIconSelect].join("\n");

  assert.match(source, /import \{[\s\S]*Input[\s\S]*PickerTrigger/);
  assert.match(providerSelect, /<PickerTrigger[\s\S]*selected=\{!!selected\}/);
  assert.match(modelIconSelect, /<PickerTrigger[\s\S]*selected=\{!!selected\}/);
  assert.match(source, /<Input[\s\S]*searchRef/);
  assert.doesNotMatch(source, /className="glass-input/);
  assert.doesNotMatch(source, /<input[\s\S]*searchRef/);
});

test("normal skill form uses shared primitives for generic form controls", () => {
  const source = readSource("../../skill/SkillFormNormal.tsx");

  assert.match(
    source,
    /import \{[\s\S]*Button[\s\S]*IconButton[\s\S]*Input[\s\S]*Textarea/,
  );
  assert.match(source, /<Input[\s\S]*skills\.form\.namePlaceholder/);
  assert.match(source, /<Textarea[\s\S]*skills\.form\.descriptionPlaceholder/);
  assert.match(source, /<Input[\s\S]*adminMarketplace\.tagsPlaceholder/);
  assert.match(source, /<Input[\s\S]*skills\.form\.filePathPlaceholder/);
  assert.match(source, /<IconButton[\s\S]*addFile/);
  assert.match(source, /<IconButton[\s\S]*editFullscreen/);
  assert.match(source, /icon=\{<Pencil size=\{15\} \/>/);
  assert.match(source, /<IconButton[\s\S]*toggleFullscreen\(true\)/);
  assert.match(source, /<Button[\s\S]*type="submit"/);
  assert.doesNotMatch(
    source,
    /<input[\s\S]*(a\.name|a\.tagsInput|updateFilePath)/,
  );
  assert.doesNotMatch(source, /<textarea[\s\S]*a\.description/);
});

test("profile password form uses shared primitives for generic controls", () => {
  const source = readSource("../../profile/tabs/ProfilePasswordTab.tsx");

  assert.match(source, /import \{[\s\S]*Button[\s\S]*IconButton[\s\S]*Input/);
  assert.match(source, /<Input[\s\S]*profile\.oldPassword/);
  assert.match(source, /<Input[\s\S]*profile\.newPassword/);
  assert.match(source, /<Input[\s\S]*profile\.confirmPassword/);
  assert.match(source, /const visibilityToggle = \([\s\S]*<IconButton/);
  assert.match(source, /trailingSlot=\{visibilityToggle\}/);
  assert.match(source, /<Button[\s\S]*handlePasswordChange/);
  assert.doesNotMatch(source, /<input[\s\S]*Password/);
  assert.doesNotMatch(source, /LoadingSpinner/);
});

test("profile info editor uses shared primitives for generic controls", () => {
  const source = readSource("../../profile/tabs/ProfileInfoTab.tsx");

  assert.match(source, /import \{[\s\S]*Button[\s\S]*IconButton[\s\S]*Input/);
  assert.match(source, /<Input[\s\S]*profile\.usernamePlaceholder/);
  assert.match(source, /<Button[\s\S]*handleAvatarDelete/);
  assert.match(source, /<Button[\s\S]*handleUsernameUpdate/);
  assert.match(source, /<IconButton[\s\S]*setIsEditingUsername\(true\)/);
  assert.doesNotMatch(source, /<input\b[^>]*value=\{newUsername\}/);
  assert.doesNotMatch(source, /<button[\s\S]*handleUsernameUpdate/);
  assert.doesNotMatch(source, /<button[\s\S]*handleAvatarDelete/);
});

test("skills list actions use shared buttons for generic commands", () => {
  const source = [
    readSource("../../panels/SkillsPanel/SkillsList.tsx"),
    readSource("../../panels/SkillsPanel/BatchActionBar.tsx"),
  ].join("\n");

  assert.match(source, /import \{ Button, IconButton \}/);
  assert.match(source, /<Button[\s>]/);
  assert.match(source, /<IconButton[\s>]/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary|icon)[^"]*"/);
});

test("marketplace panel generic actions use shared buttons", () => {
  const source = readSource("../../panels/MarketplacePanel.tsx");

  assert.match(source, /import \{ Button, IconButton \}/);
  assert.match(source, /<Button[\s>]/);
  assert.match(source, /<IconButton[\s>]/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary|icon)[^"]*"/);
});

test("small reusable panel controls use shared panel primitives where generic", () => {
  const memoryFilter = readSource("../../panels/MemoryPanel/MemoryFilter.tsx");
  const mcpServerCard = readSource("../../mcp/MCPServerCard.tsx");

  assert.match(memoryFilter, /import \{ PanelFilterSelect \}/);
  assert.match(memoryFilter, /<PanelFilterSelect[\s\S]*typeOnChange/);
  assert.match(memoryFilter, /<PanelFilterSelect[\s\S]*sourceOnChange/);
  assert.doesNotMatch(memoryFilter, /import \{ Button \}/);
  assert.doesNotMatch(memoryFilter, /import \{ Select \}/);
  assert.doesNotMatch(memoryFilter, /<Button[\s\S]*panel-filter-trigger/);
  assert.doesNotMatch(memoryFilter, /className="btn-secondary[^"]*"/);

  assert.match(mcpServerCard, /import \{ IconButton \}/);
  assert.match(mcpServerCard, /<IconButton[\s\S]*onEdit\(server\)/);
  assert.match(mcpServerCard, /<IconButton[\s\S]*onDelete\(server\.name/);
  assert.doesNotMatch(mcpServerCard, /className="btn-icon[^"]*"/);
});

test("memory panel generic actions and editor fields use shared primitives", () => {
  const memoryPanel = readSource("../../panels/MemoryPanel/index.tsx");
  const memoryEditor = readSource("../../panels/MemoryPanel/MemoryEditor.tsx");
  const detailModal = readSource("../../panels/MemoryPanel/DetailModal.tsx");

  assert.match(memoryPanel, /import \{ Button, IconButton \}/);
  assert.match(memoryPanel, /<Button[\s\S]*setEditingMemory\(null\)/);
  assert.match(memoryPanel, /<IconButton[\s\S]*setEditingMemory\(memory\)/);
  assert.match(
    memoryPanel,
    /<IconButton[\s\S]*setDeleteId\(memory\.memory_id\)/,
  );
  assert.doesNotMatch(
    memoryPanel,
    /className="btn-(primary|secondary|icon)[^"]*"/,
  );

  assert.match(memoryEditor, /PanelFooterActions/);
  assert.match(
    memoryEditor,
    /import \{[\s\S]*Button[\s\S]*FormField[\s\S]*Input[\s\S]*PanelFooterActions[\s\S]*Textarea[\s\S]*\}/,
  );
  assert.match(memoryEditor, /<FormField[\s\S]*memory\.titleLabel/);
  assert.match(memoryEditor, /<Input[\s\S]*memory\.titlePlaceholder/);
  assert.match(memoryEditor, /<Textarea[\s\S]*memory\.contentPlaceholder/);
  assert.doesNotMatch(memoryEditor, /className="btn-(primary|secondary)[^"]*"/);
  assert.doesNotMatch(memoryEditor, /className="glass-input/);

  assert.match(detailModal, /import \{ Button, PanelFooterActions \}/);
  assert.match(detailModal, /PanelFooterActions/);
  assert.match(detailModal, /<Button[\s\S]*variant="danger"/);
  assert.doesNotMatch(detailModal, /className="btn-(danger|secondary)[^"]*"/);
});

test("mcp panel generic shell actions use shared buttons", () => {
  const source = readSource("../../panels/MCPPanel.tsx");

  assert.match(
    source,
    /import \{[\s\S]*Button[\s\S]*Checkbox[\s\S]*IconButton[\s\S]*PanelFooterActions[\s\S]*Textarea[\s\S]*\}/,
  );
  assert.match(source, /PanelFooterActions/);
  assert.match(source, /<Button[\s\S]*handleImportClick/);
  assert.match(source, /<Button[\s\S]*handleCreate/);
  assert.match(source, /<IconButton[\s\S]*clearError/);
  assert.match(source, /<Checkbox[\s\S]*createAsSystem/);
  assert.match(source, /<Checkbox[\s\S]*changeToSystem/);
  assert.match(source, /<Checkbox[\s\S]*importOverwrite/);
  assert.match(source, /<Textarea[\s\S]*importJson/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary|icon)[^"]*"/);
  assert.doesNotMatch(source, /className="glass-input es-textarea/);
  assert.doesNotMatch(source, /<input[\s\S]*type="checkbox"/);
});

test("mcp tool expanded settings expose inline function policy toggle", () => {
  const source = readSource("../../mcp/MCPServerToolsSidebar.tsx");

  assert.match(source, /server\.can_edit\s*&&\s*server\.is_system/);
  assert.match(source, /mcp\.form\.inlineExposure/);
  assert.match(source, /mcp\.form\.inlineExposureDescription/);
  assert.match(source, /inline_exposure:\s*!\(tool\.inline_exposure/);
  assert.match(source, /mcpApi\.updateToolPolicy[\s\S]*inline_exposure/);
});

test("core admin crud panels use shared panel controls for generic actions", () => {
  const sources = [
    readSource("../../panels/NotificationPanel.tsx"),
    readSource("../../../plugins/feedback/FeedbackPanel.tsx"),
    readSource("../../panels/UsersPanel.tsx"),
    readSource("../../panels/RolesPanel.tsx"),
  ].join("\n");
  const feedbackCompatibility = readSource("../../panels/FeedbackPanel.tsx");

  assert.match(sources, /PanelFilterSelect/);
  assert.match(sources, /PanelFooterActions/);
  assert.match(sources, /<Button[\s>]/);
  assert.match(
    feedbackCompatibility,
    /export \{ FeedbackPanel \} from "\.\.\/\.\.\/plugins\/feedback\/FeedbackPanel"/,
  );
  assert.doesNotMatch(
    sources,
    /className="btn-(primary|secondary|danger|icon)[^"]*"/,
  );
  assert.doesNotMatch(sources, /<GlassSelect/);
});

test("notification admin modal fields use shared field primitives", () => {
  const source = readSource("../../panels/NotificationPanel.tsx");

  assert.match(source, /import \{[\s\S]*Input[\s\S]*Textarea/);
  assert.match(source, /<Input[\s\S]*notification\.titleLabel/);
  assert.match(source, /<Textarea[\s\S]*notification\.contentLabel/);
  assert.match(source, /<Input[\s\S]*notification\.startTime/);
  assert.match(source, /<Input[\s\S]*notification\.endTime/);
  assert.doesNotMatch(source, /<input[\s\S]*titleI18n/);
  assert.doesNotMatch(source, /<textarea[\s\S]*contentI18n/);
});

test("roles admin form uses shared field primitives for generic fields", () => {
  const source = readSource("../../panels/RolesPanel.tsx");

  assert.match(
    source,
    /import \{[\s\S]*Button[\s\S]*Input[\s\S]*PanelFooterActions[\s\S]*Textarea[\s\S]*\}/,
  );
  assert.match(source, /<Input[\s\S]*roles\.roleNamePlaceholder/);
  assert.match(source, /<Textarea[\s\S]*roles\.descriptionPlaceholder/);
  assert.doesNotMatch(source, /className="glass-input/);
});

test("model admin modal footers use shared panel actions", () => {
  const source = [
    readSource("../../panels/ModelPanel/tabs/ModelFormModal.tsx"),
    readSource("../../panels/ModelPanel/tabs/BatchCreateModal.tsx"),
  ].join("\n");

  assert.match(source, /PanelFooterActions/);
  assert.match(source, /<Button[\s>]/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary)[^"]*"/);
});

test("model admin modal form bodies use shared field primitives", () => {
  const modelForm = readSource(
    "../../panels/ModelPanel/tabs/ModelFormModal.tsx",
  );
  const batchCreate = readSource(
    "../../panels/ModelPanel/tabs/BatchCreateModal.tsx",
  );
  const source = [modelForm, batchCreate].join("\n");

  assert.match(source, /import \{ Checkbox \}/);
  assert.match(source, /import \{[\s\S]*Input[\s\S]*Select[\s\S]*Textarea/);
  assert.match(modelForm, /<Select[\s\S]*formFallbackModel/);
  assert.match(modelForm, /<Checkbox[\s\S]*checked=\{formSupportsVision\}/);
  assert.match(batchCreate, /<Textarea[\s\S]*importJson/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /className="glass-input/);
  assert.doesNotMatch(source, /<input[\s\S]*type="checkbox"/);
});

test("agent and model admin shells use shared buttons for header commands", () => {
  const source = [
    readSource("../../panels/AgentPanel/AgentConfigPanel.tsx"),
    readSource("../../panels/ModelPanel/ModelPanel.tsx"),
  ].join("\n");

  assert.match(source, /import \{ Button \}/);
  assert.match(source, /<Button[\s\S]*handleRefresh/);
  assert.doesNotMatch(source, /className="btn-secondary[^"]*"/);
});

test("agent and model admin tab actions use shared buttons", () => {
  const sources = [
    readSource("../../panels/AgentPanel/tabs/GlobalAgentTab.tsx"),
    readSource("../../panels/AgentPanel/tabs/RolesAgentTab.tsx"),
    readSource("../../panels/ModelPanel/tabs/ModelConfigTab.tsx"),
    readSource("../../panels/ModelPanel/tabs/RolesModelTab.tsx"),
  ].join("\n");

  assert.match(sources, /import \{[\s\S]*Button[\s\S]*\}/);
  assert.match(sources, /<Button[\s\S]*agentConfig\.addModel/);
  assert.match(sources, /<Button[\s\S]*common\.save/);
  assert.doesNotMatch(sources, /className="btn-(primary|secondary)[^"]*"/);
});

test("global agent editor fields use shared field primitives", () => {
  const source = readSource("../../panels/AgentPanel/tabs/GlobalAgentTab.tsx");

  assert.match(source, /import \{[\s\S]*Input[\s\S]*Textarea[\s\S]*\}/);
  assert.match(source, /<Input[\s\S]*sort_order/);
  assert.match(source, /<Input[\s\S]*agentConfig\.displayName/);
  assert.match(source, /<Textarea[\s\S]*agentConfig\.displayDescription/);
  assert.doesNotMatch(source, /className="glass-input/);
});

test("roles agent assignments use the shared checkbox primitive", () => {
  const source = readSource("../../panels/AgentPanel/tabs/RolesAgentTab.tsx");

  assert.match(source, /import \{ Checkbox \}/);
  assert.match(source, /<Checkbox[\s\S]*checked=\{isSelected\}/);
  assert.doesNotMatch(source, /<input[\s\S]*type="checkbox"/);
});

test("channel panel generic controls use shared primitives", () => {
  const source = readSource("../../panels/ChannelPanel.tsx");

  assert.match(source, /import \{[\s\S]*Button[\s\S]*Input[\s\S]*Select/);
  assert.match(source, /<Select[\s\S]*field\.options/);
  assert.match(source, /<Input[\s\S]*channel\.instanceNamePlaceholder/);
  assert.match(source, /<Button[\s\S]*handleSave/);
  assert.match(source, /<Button[\s\S]*handleDeleteClick/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /className="[^"]*glass-input/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary|danger)/);
});

test("settings panel generic controls use shared primitives", () => {
  const source = readSource("../../panels/SettingsPanel.tsx");

  assert.match(
    source,
    /import \{[\s\S]*Button[\s\S]*Input[\s\S]*Select[\s\S]*Textarea/,
  );
  assert.match(source, /<Select[\s\S]*CATEGORY_ORDER/);
  assert.match(source, /<Select[\s\S]*DEFAULT_AGENT/);
  assert.match(source, /setting\.type === "text"[\s\S]*<Textarea/);
  assert.match(source, /<Input[\s\S]*setting\.type === "number"/);
  assert.match(source, /<Button[\s\S]*handleExport/);
  assert.match(source, /<Button[\s\S]*handleSave\(setting\)/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary|danger)/);
});

test("json schema editor uses shared primitives for generated controls", () => {
  const source = readSource("../../panels/JsonSchemaEditor.tsx");

  assert.match(source, /import \{ Button, IconButton, Input, Select \}/);
  assert.match(source, /<Select[\s\S]*field\.options/);
  assert.match(source, /<Input[\s\S]*field\.placeholder/);
  assert.match(source, /<IconButton[\s\S]*removeItem/);
  assert.match(source, /<Button[\s\S]*JSON_SCHEMA_ADD_ITEM/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /<input[\s\S]*field\.placeholder/);
});

test("approval panel generated form fields use shared field primitives", () => {
  const source = readSource("../../panels/ApprovalPanel.tsx");

  assert.match(source, /import \{[\s\S]*Input[\s\S]*Select[\s\S]*Textarea/);
  assert.match(source, /case "text":[\s\S]*<Input/);
  assert.match(source, /case "number":[\s\S]*<Input/);
  assert.match(source, /case "textarea":[\s\S]*<Textarea/);
  assert.match(source, /case "select":[\s\S]*<Select/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /<input[\s\S]*approval-input/);
  assert.doesNotMatch(source, /<textarea[\s\S]*approval-input/);
});

test("scheduled task form uses shared primitives for generic form controls", () => {
  const source = readSource(
    "../../panels/ScheduledTaskPanel/TaskFormModal.tsx",
  );

  assert.match(
    source,
    /import \{[\s\S]*Button[\s\S]*Input[\s\S]*PanelFooterActions[\s\S]*Select[\s\S]*Textarea/,
  );
  assert.match(source, /<PanelFooterActions/);
  assert.match(source, /<Button[\s\S]*handleSave/);
  assert.match(source, /<Input[\s\S]*scheduledTask\.namePlaceholder/);
  assert.match(source, /<Textarea[\s\S]*scheduledTask\.descriptionPlaceholder/);
  assert.match(source, /<Select[\s\S]*scheduledTask\.agentPlaceholder/);
  assert.match(source, /<Select[\s\S]*scheduledTask\.modelPlaceholder/);
  assert.doesNotMatch(source, /GlassSelect/);
  assert.doesNotMatch(source, /className="btn-(primary|secondary)[^"]*"/);
  assert.doesNotMatch(source, /<input[\s\S]*scheduled-task-input/);
  assert.doesNotMatch(source, /<textarea[\s\S]*scheduled-task-input/);
});
