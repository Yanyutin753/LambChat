import { readFileSync } from "node:fs";
function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function assertExports(source: string, name: string): void {
  expect(source).toMatch(
    new RegExp(`export \\{[\\s\\S]*\\b${name}\\b[\\s\\S]*\\} from`),
  );
}

function assertCssSelector(source: string, selector: string): void {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  expect(source).toMatch(new RegExp(`${escaped}[\\s\\S]*?\\{`));
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

  expect(uiIndex).toMatch(/export type \{ ButtonVariant, ButtonSize \}/);
  expect(uiIndex).toMatch(/export type \{ SelectOption \}/);
});

test("common panel controls are exposed for consistent admin panel composition", () => {
  const commonIndex = readSource("../index.ts");
  const panelControls = readSource("../PanelControls.tsx");

  for (const name of ["PanelFilterSelect", "PanelFooterActions"]) {
    assertExports(commonIndex, name);
  }

  expect(panelControls).toMatch(/import \{ Select \}/);
  expect(panelControls).toMatch(/panel-filter-select/);
  expect(panelControls).toMatch(/panel-footer-actions/);
});

test("toolbar icon button centralizes shared panel toolbar button behavior", () => {
  const commonIndex = readSource("../index.ts");
  const uiIndex = readSource("../ui/index.ts");
  const toolbarIconButton = readSource("../ui/ToolbarIconButton.tsx");
  const documentToolbar = readSource(
    "../../documents/DocumentPreviewToolbar.tsx",
  );
  const revealPreviewHost = readSource(
    "../../chat/ChatMessage/items/RevealPreviewHost.tsx",
  );
  const toolResultPanel = readSource(
    "../../chat/ChatMessage/items/ToolResultPanel.tsx",
  );

  assertExports(uiIndex, "ToolbarIconButton");
  assertExports(commonIndex, "ToolbarIconButton");
  expect(toolbarIconButton).toMatch(
    /type ToolbarIconButtonVariant = "stone" \| "muted"/,
  );
  expect(toolbarIconButton).toMatch(/stopPropagation\(\)/);
  expect(toolbarIconButton).toMatch(
    /flex shrink-0 items-center justify-center/,
  );
  expect(toolbarIconButton).toMatch(
    /min-h-\[44px\].*min-w-\[44px\].*sm:size-8/,
  );
  expect(toolbarIconButton).toMatch(/focus-visible:ring-2/);
  expect(toolbarIconButton).toMatch(/rounded-lg/);
  expect(toolbarIconButton).toMatch(/rounded-xl/);

  expect(documentToolbar).toMatch(/import \{[\s\S]*ToolbarIconButton/);
  expect(toolResultPanel).toMatch(/import \{[\s\S]*ToolbarIconButton/);
  expect(documentToolbar).not.toMatch(/const toolbarBtnClass/);
  expect(toolResultPanel).not.toMatch(/const panelBtnClass/);
  expect(toolResultPanel).not.toMatch(/const panelCloseBtnClass/);
  expect(documentToolbar).toMatch(/gap-2\.5 sm:gap-1 relative/);
  expect(revealPreviewHost).toMatch(
    /headerActions=[\s\S]*?<ToolbarIconButton[\s\S]*?aria-pressed=/,
  );
  expect(revealPreviewHost).not.toMatch(
    /headerActions=[\s\S]*?w-8 h-8[\s\S]*?toggleExplorer/,
  );
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
  expect(floatingIconButton).toMatch(/fixed right-4 z-\[410\]/);
  expect(floatingIconButton).toMatch(
    /flex shrink-0 items-center justify-center/,
  );
  expect(floatingIconButton).toMatch(/w-11 h-11 rounded-xl bg-black\/80/);

  expect(documentToolbar).toMatch(/import \{[\s\S]*FloatingIconButton/);
  expect(skillFullscreen).toMatch(/import \{ FloatingIconButton \}/);
  expect(documentToolbar).not.toMatch(/w-11 h-11 rounded-xl bg-black\/80/);
  expect(skillFullscreen).not.toMatch(/w-11 h-11 rounded-xl bg-black\/80/);
});

test("viewer toolbar uses a fixed-size reusable icon button for overlay controls", () => {
  const source = readSource("../ViewerToolbar.tsx");

  expect(source).toMatch(/function ViewerToolbarButton/);
  expect(source).toMatch(/flex shrink-0 items-center justify-center size-8/);
  expect(source).toMatch(/disabled:opacity-50 disabled:cursor-not-allowed/);
  expect(source).toMatch(/<ViewerToolbarButton[\s\S]*imageViewer\.rotateLeft/);
  expect(source).toMatch(/<ViewerToolbarButton[\s\S]*imageViewer\.zoomOut/);
  expect(source).toMatch(/<ViewerToolbarButton[\s\S]*imageViewer\.reset/);
  expect(source).not.toMatch(
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
  expect(topBar).toMatch(/safe-area-top bg-black/);
  expect(topBar).toMatch(/flex h-16 items-center justify-between px-3 sm:px-6/);
  assertExports(commonIndex, "ViewerTopBarButton");
  expect(source).toMatch(/flex shrink-0/);
  expect(source).toMatch(/whitespace-nowrap/);
  expect(source).toMatch(/w-10 h-10/);
  expect(source).toMatch(/px-3 h-10/);
  expect(source).toMatch(/disabled:opacity-50 disabled:cursor-not-allowed/);

  expect(imageViewer).toMatch(/import \{ ViewerTopBarButton \}/);
  expect(videoViewer).toMatch(/import \{ ViewerTopBarButton \}/);
  expect(imageViewer).toMatch(/import \{ ViewerTopBar \}/);
  expect(videoViewer).toMatch(/import \{ ViewerTopBar \}/);
  expect(mermaidViewer).toMatch(/import \{[\s\S]*ViewerTopBar/);
  expect(excalidrawViewer).toMatch(/import \{[\s\S]*ViewerTopBar/);
  expect(imageViewer).toMatch(/<ViewerTopBarButton[\s\S]*common\.close/);
  expect(videoViewer).toMatch(/<ViewerTopBarButton[\s\S]*common\.close/);
  expect(mermaidViewer).toMatch(/import \{[\s\S]*ViewerTopBarButton/);
  expect(excalidrawViewer).toMatch(/import \{[\s\S]*ViewerTopBarButton/);
  expect(mermaidViewer).toMatch(/<ViewerTopBarButton[\s\S]*common\.close/);
  expect(mermaidViewer).toMatch(
    /<ViewerTopBarButton[\s\S]*imageViewer\.download/,
  );
  expect(excalidrawViewer).toMatch(/<ViewerTopBarButton[\s\S]*common\.close/);
  expect(excalidrawViewer).toMatch(
    /<ViewerTopBarButton[\s\S]*documents\.download/,
  );
  expect(
    [imageViewer, videoViewer, mermaidViewer, excalidrawViewer].join("\n"),
  ).not.toMatch(
    /className=\{?btnCls\}?|className="flex items-center (?:justify-center w-10 h-10|gap-1\.5 rounded-lg px-3 h-10[^"]*text-white\/70)/,
  );
});

test("image and video viewers share direct URL download behavior", () => {
  const commonIndex = readSource("../index.ts");
  const helper = readSource("../viewerDownload.ts");
  const imageViewer = readSource("../ImageViewer.tsx");
  const videoViewer = readSource("../VideoViewer.tsx");

  assertExports(commonIndex, "downloadUrl");
  expect(helper).toMatch(/export function downloadUrl/);
  expect(helper).toMatch(/document\.createElement\("a"\)/);
  expect(helper).toMatch(/anchor\.download = fileName \?\? ""/);
  expect(helper).toMatch(/anchor\.click\(\)/);

  expect(imageViewer).toMatch(/import \{ downloadUrl \}/);
  expect(videoViewer).toMatch(/import \{ downloadUrl \}/);
  expect(imageViewer).toMatch(/onClick=\{\(\) => downloadUrl\(src\)\}/);
  expect(videoViewer).toMatch(/onClick=\{\(\) => downloadUrl\(src\)\}/);
  expect([imageViewer, videoViewer].join("\n")).not.toMatch(
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
  expect(helper).toMatch(/export function downloadBlob/);
  expect(helper).toMatch(/URL\.createObjectURL\(blob\)/);
  expect(helper).toMatch(/downloadUrl\(url, fileName\)/);
  expect(helper).toMatch(/URL\.revokeObjectURL\(url\)/);
  assertExports(commonIndex, "ViewerDropdownMenuItem");
  expect(menuItem).toMatch(
    /type ViewerDropdownMenuItemVariant = "stone" \| "dark"/,
  );
  expect(menuItem).toMatch(/whitespace-nowrap/);

  expect(mermaidViewer).toMatch(/import \{ downloadBlob \}/);
  expect(mermaidViewer).toMatch(/import \{[\s\S]*ViewerDropdownMenuItem/);
  expect(documentMermaidViewer).toMatch(/import \{ downloadBlob \}/);
  expect(documentMermaidViewer).toMatch(
    /import \{[\s\S]*ViewerDropdownMenuItem/,
  );
  expect(excalidrawViewer).toMatch(/import \{ downloadBlob \}/);
  expect(excalidrawViewer).toMatch(/import \{[\s\S]*ViewerDropdownMenuItem/);
  expect(mermaidViewer).toMatch(/downloadBlob\([^)]*"diagram\.svg"/);
  expect(mermaidViewer).toMatch(/downloadBlob\([^)]*"diagram\.png"/);
  expect(mermaidViewer).toMatch(/downloadBlob\([^)]*"mermaid\.svg"/);
  expect(mermaidViewer).toMatch(/<ViewerDropdownMenuItem[\s\S]*SVG/);
  expect(mermaidViewer).toMatch(/<ViewerDropdownMenuItem[\s\S]*PNG/);
  expect(documentMermaidViewer).toMatch(/downloadBlob\([^)]*"diagram\.svg"/);
  expect(documentMermaidViewer).toMatch(/downloadBlob\([^)]*"diagram\.png"/);
  expect(documentMermaidViewer).toMatch(/<ViewerDropdownMenuItem[\s\S]*SVG/);
  expect(documentMermaidViewer).toMatch(/<ViewerDropdownMenuItem[\s\S]*PNG/);
  expect(excalidrawViewer).toMatch(
    /downloadBlob\([^)]*"excalidraw-diagram\.svg"/,
  );
  expect(excalidrawViewer).toMatch(
    /downloadBlob\([^)]*"excalidraw-diagram\.png"/,
  );
  expect(excalidrawViewer).toMatch(
    /<ViewerDropdownMenuItem[\s\S]*variant="dark"[\s\S]*SVG/,
  );
  expect(excalidrawViewer).toMatch(
    /<ViewerDropdownMenuItem[\s\S]*variant="dark"[\s\S]*PNG/,
  );
  expect(
    [mermaidViewer, documentMermaidViewer, excalidrawViewer].join("\n"),
  ).not.toMatch(
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
  expect(source).toMatch(/flex shrink-0 items-center justify-center/);
  expect(source).toMatch(/w-10 h-10 rounded-full bg-black\/70/);
  expect(source).toMatch(/hover:bg-black\/90 text-white shadow-lg/);

  expect(toolResultPanel).toMatch(/import \{[\s\S]*ToolbarIconButton/);
  expect(toolResultPanel).not.toMatch(/OverlayRoundIconButton/);
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

  expect(css).toMatch(/\.btn-primary\s*\{[\s\S]*?\.ui-button--primary/);
  expect(css).toMatch(/\.glass-input\.es-input\s*\{[\s\S]*?\.ui-input/);

  // The standalone .ui-button__label block (not the nested .panel-filter-trigger variant)
  const standaloneButtonLabel = css.match(/^\.ui-button__label\s*\{([^}]*)\}/m);
  expect(standaloneButtonLabel).toBeTruthy();
  expect(standaloneButtonLabel![1]).toMatch(/display:\s*inline-flex/);
  expect(standaloneButtonLabel![1]).toMatch(/white-space:\s*nowrap/);
});

test("legacy GlassSelect delegates to the shared Select primitive", () => {
  const source = readSource("../GlassSelect.tsx");

  expect(source).toMatch(/import \{ Select \}/);
  expect(source).toMatch(/return \([\s\S]*<Select/);
  expect(source).toMatch(
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

  expect(migratedSources).toMatch(/import \{ Button/);
  expect(migratedSources).toMatch(
    /import \{ Button, FormField, Input, Textarea \}/,
  );
  expect(migratedSources).toMatch(/<Button[\s>]/);
  expect(migratedSources).toMatch(/<Input[\s>]/);
  expect(migratedSources).toMatch(/<Textarea[\s>]/);
  expect(migratedSources).toMatch(/<FormField[\s>]/);
  expect(migratedSources).not.toMatch(
    /className="btn-(primary|secondary)[^"]*"/,
  );
  expect(migratedSources).not.toMatch(/className="input-field[^"]*"/);
});

test("mcp server form uses shared icon buttons for generic icon actions", () => {
  const source = readSource("../../mcp/MCPServerForm.tsx");

  expect(source).toMatch(/import \{ Button, IconButton, Input, Select \}/);
  expect(source).toMatch(/<Select[\s\S]*availableTransports/);
  expect(source).toMatch(/<Input[\s\S]*mcp\.form\.serverNamePlaceholder/);
  expect(source).toMatch(/<IconButton[\s\S]*removeHeader/);
  expect(source).not.toMatch(/className="btn-icon[^"]*"/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/className="glass-input/);
});

test("custom admin pickers reuse shared picker trigger and input primitives", () => {
  const providerSelect = readSource(
    "../../panels/AgentPanel/shared/ProviderSelect.tsx",
  );
  const modelIconSelect = readSource(
    "../../panels/ModelPanel/tabs/ModelIconSelect.tsx",
  );
  const source = [providerSelect, modelIconSelect].join("\n");

  expect(source).toMatch(/import \{[\s\S]*Input[\s\S]*PickerTrigger/);
  expect(providerSelect).toMatch(
    /<PickerTrigger[\s\S]*selected=\{!!selected\}/,
  );
  expect(modelIconSelect).toMatch(
    /<PickerTrigger[\s\S]*selected=\{!!selected\}/,
  );
  expect(source).toMatch(/<PanelSearchInput[\s\S]*searchRef/);
  expect(source).not.toMatch(/className="glass-input/);
  expect(source).not.toMatch(/<input[\s\S]*searchRef/);
});

test("normal skill form uses shared primitives for generic form controls", () => {
  const source = readSource("../../skill/SkillFormNormal.tsx");

  expect(source).toMatch(
    /import \{[\s\S]*Button[\s\S]*IconButton[\s\S]*Input[\s\S]*Textarea/,
  );
  expect(source).toMatch(/<Input[\s\S]*skills\.form\.namePlaceholder/);
  expect(source).toMatch(
    /<Textarea[\s\S]*skills\.form\.descriptionPlaceholder/,
  );
  expect(source).toMatch(/<Input[\s\S]*adminMarketplace\.tagsPlaceholder/);
  expect(source).toMatch(/<Input[\s\S]*skills\.form\.filePathPlaceholder/);
  expect(source).toMatch(/<IconButton[\s\S]*addFile/);
  expect(source).toMatch(/<IconButton[\s\S]*editFullscreen/);
  expect(source).toMatch(/icon=\{<Pencil size=\{15\} \/>/);
  expect(source).toMatch(/<IconButton[\s\S]*toggleFullscreen\(true\)/);
  expect(source).toMatch(/<Button[\s\S]*type="submit"/);
  expect(source).not.toMatch(
    /<input[\s\S]*(a\.name|a\.tagsInput|updateFilePath)/,
  );
  expect(source).not.toMatch(/<textarea[\s\S]*a\.description/);
});

test("profile password form uses shared primitives for generic controls", () => {
  const source = readSource("../../profile/tabs/ProfilePasswordTab.tsx");

  expect(source).toMatch(/import \{[\s\S]*Button[\s\S]*IconButton[\s\S]*Input/);
  expect(source).toMatch(/<Input[\s\S]*profile\.oldPassword/);
  expect(source).toMatch(/<Input[\s\S]*profile\.newPassword/);
  expect(source).toMatch(/<Input[\s\S]*profile\.confirmPassword/);
  expect(source).toMatch(/const visibilityToggle = \([\s\S]*<IconButton/);
  expect(source).toMatch(/trailingSlot=\{visibilityToggle\}/);
  expect(source).toMatch(/<Button[\s\S]*handlePasswordChange/);
  expect(source).not.toMatch(/<input[\s\S]*Password/);
  expect(source).not.toMatch(/LoadingSpinner/);
});

test("profile info editor uses shared primitives for generic controls", () => {
  const source = readSource("../../profile/tabs/ProfileInfoTab.tsx");

  expect(source).toMatch(/import \{[\s\S]*Button[\s\S]*IconButton[\s\S]*Input/);
  expect(source).toMatch(/<Input[\s\S]*profile\.usernamePlaceholder/);
  expect(source).toMatch(/<Button[\s\S]*handleAvatarDelete/);
  expect(source).toMatch(/<Button[\s\S]*handleUsernameUpdate/);
  expect(source).toMatch(/<IconButton[\s\S]*setIsEditingUsername\(true\)/);
  expect(source).not.toMatch(/<input\b[^>]*value=\{newUsername\}/);
  expect(source).not.toMatch(/<button[\s\S]*handleUsernameUpdate/);
  expect(source).not.toMatch(/<button[\s\S]*handleAvatarDelete/);
});

test("skills list actions use shared buttons for generic commands", () => {
  const source = [
    readSource("../../panels/SkillsPanel/SkillsList.tsx"),
    readSource("../../panels/SkillsPanel/BatchActionBar.tsx"),
  ].join("\n");

  expect(source).toMatch(/import \{ Button, IconButton \}/);
  expect(source).toMatch(/<Button[\s>]/);
  expect(source).toMatch(/<IconButton[\s>]/);
  expect(source).not.toMatch(/className="btn-(primary|secondary|icon)[^"]*"/);
});

test("marketplace panel generic actions use shared buttons", () => {
  const source = readSource("../../panels/MarketplacePanel.tsx");

  expect(source).toMatch(/import \{ Button, IconButton \}/);
  expect(source).toMatch(/<Button[\s>]/);
  expect(source).toMatch(/<IconButton[\s>]/);
  expect(source).not.toMatch(/className="btn-(primary|secondary|icon)[^"]*"/);
});

test("small reusable panel controls use shared panel primitives where generic", () => {
  const memoryFilter = readSource("../../panels/MemoryPanel/MemoryFilter.tsx");
  const mcpServerCard = readSource("../../mcp/MCPServerCard.tsx");

  expect(memoryFilter).toMatch(/import \{ PanelFilterSelect \}/);
  expect(memoryFilter).toMatch(/<PanelFilterSelect[\s\S]*typeOnChange/);
  expect(memoryFilter).toMatch(/<PanelFilterSelect[\s\S]*sourceOnChange/);
  expect(memoryFilter).not.toMatch(/import \{ Button \}/);
  expect(memoryFilter).not.toMatch(/import \{ Select \}/);
  expect(memoryFilter).not.toMatch(/<Button[\s\S]*panel-filter-trigger/);
  expect(memoryFilter).not.toMatch(/className="btn-secondary[^"]*"/);

  expect(mcpServerCard).toMatch(/import \{ IconButton \}/);
  expect(mcpServerCard).toMatch(/<IconButton[\s\S]*onEdit\(server\)/);
  expect(mcpServerCard).toMatch(/<IconButton[\s\S]*onDelete\(server\.name/);
  expect(mcpServerCard).not.toMatch(/className="btn-icon[^"]*"/);
});

test("memory panel generic actions and editor fields use shared primitives", () => {
  const memoryPanel = readSource("../../panels/MemoryPanel/index.tsx");
  const memoryEditor = readSource("../../panels/MemoryPanel/MemoryEditor.tsx");
  const detailModal = readSource("../../panels/MemoryPanel/DetailModal.tsx");

  expect(memoryPanel).toMatch(/import \{ Button, IconButton \}/);
  expect(memoryPanel).toMatch(/<Button[\s\S]*setEditingMemory\(null\)/);
  expect(memoryPanel).toMatch(/<IconButton[\s\S]*setEditingMemory\(memory\)/);
  expect(memoryPanel).toMatch(
    /<IconButton[\s\S]*setDeleteId\(memory\.memory_id\)/,
  );
  expect(memoryPanel).not.toMatch(
    /className="btn-(primary|secondary|icon)[^"]*"/,
  );

  expect(memoryEditor).toMatch(/PanelFooterActions/);
  expect(memoryEditor).toMatch(
    /import \{[\s\S]*Button[\s\S]*FormField[\s\S]*Input[\s\S]*PanelFooterActions[\s\S]*Textarea[\s\S]*\}/,
  );
  expect(memoryEditor).toMatch(/<FormField[\s\S]*memory\.titleLabel/);
  expect(memoryEditor).toMatch(/<Input[\s\S]*memory\.titlePlaceholder/);
  expect(memoryEditor).toMatch(/<Textarea[\s\S]*memory\.contentPlaceholder/);
  expect(memoryEditor).not.toMatch(/className="btn-(primary|secondary)[^"]*"/);
  expect(memoryEditor).not.toMatch(/className="glass-input/);

  expect(detailModal).toMatch(/import \{ Button, PanelFooterActions \}/);
  expect(detailModal).toMatch(/PanelFooterActions/);
  expect(detailModal).toMatch(/<Button[\s\S]*variant="danger"/);
  expect(detailModal).not.toMatch(/className="btn-(danger|secondary)[^"]*"/);
});

test("mcp panel generic shell actions use shared buttons", () => {
  const source = readSource("../../panels/MCPPanel.tsx");

  expect(source).toMatch(
    /import \{[\s\S]*Button[\s\S]*Checkbox[\s\S]*IconButton[\s\S]*PanelFooterActions[\s\S]*Textarea[\s\S]*\}/,
  );
  expect(source).toMatch(/PanelFooterActions/);
  expect(source).toMatch(/<Button[\s\S]*handleImportClick/);
  expect(source).toMatch(/<Button[\s\S]*handleCreate/);
  expect(source).toMatch(/<IconButton[\s\S]*clearError/);
  expect(source).toMatch(/<Checkbox[\s\S]*createAsSystem/);
  expect(source).toMatch(/<Checkbox[\s\S]*changeToSystem/);
  expect(source).toMatch(/<Checkbox[\s\S]*importOverwrite/);
  expect(source).toMatch(/<Textarea[\s\S]*importJson/);
  expect(source).not.toMatch(/className="btn-(primary|secondary|icon)[^"]*"/);
  expect(source).not.toMatch(/className="glass-input es-textarea/);
  expect(source).not.toMatch(/<input[\s\S]*type="checkbox"/);
});

test("mcp tool expanded settings expose inline function policy toggle", () => {
  const source = readSource("../../mcp/MCPServerToolsSidebar.tsx");

  expect(source).toMatch(/server\.can_edit\s*&&\s*server\.is_system/);
  expect(source).toMatch(/mcp\.form\.inlineExposure/);
  expect(source).toMatch(/mcp\.form\.inlineExposureDescription/);
  expect(source).toMatch(/inline_exposure:\s*!\([\s\S]*?tool\.inline_exposure/);
  expect(source).toMatch(/mcpApi\.updateToolPolicy[\s\S]*inline_exposure/);
});

test("core admin crud panels use shared panel controls for generic actions", () => {
  const sources = [
    readSource("../../panels/NotificationPanel.tsx"),
    readSource("../../panels/UsersPanel.tsx"),
    readSource("../../panels/RolesPanel.tsx"),
  ].join("\n");

  expect(sources).toMatch(/PanelFooterActions/);
  expect(sources).toMatch(/<Button[\s>]/);
  expect(sources).not.toMatch(
    /className="btn-(primary|secondary|danger|icon)[^"]*"/,
  );
  expect(sources).not.toMatch(/<GlassSelect/);
});

test("notification admin modal fields use shared field primitives", () => {
  const source = readSource("../../panels/NotificationPanel.tsx");

  expect(source).toMatch(/import \{[\s\S]*Input[\s\S]*Textarea/);
  expect(source).toMatch(/<Input[\s\S]*notification\.titleLabel/);
  expect(source).toMatch(/<Textarea[\s\S]*notification\.contentLabel/);
  expect(source).toMatch(/<Input[\s\S]*notification\.startTime/);
  expect(source).toMatch(/<Input[\s\S]*notification\.endTime/);
  expect(source).not.toMatch(/<input[\s\S]*titleI18n/);
  expect(source).not.toMatch(/<textarea[\s\S]*contentI18n/);
});

test("roles admin form uses shared field primitives for generic fields", () => {
  const source = readSource("../../panels/RolesPanel.tsx");

  expect(source).toMatch(
    /import \{[\s\S]*Button[\s\S]*Input[\s\S]*PanelFooterActions[\s\S]*Textarea[\s\S]*\}/,
  );
  expect(source).toMatch(/<Input[\s\S]*roles\.roleNamePlaceholder/);
  expect(source).toMatch(/<Textarea[\s\S]*roles\.descriptionPlaceholder/);
  expect(source).not.toMatch(/className="glass-input/);
});

test("model admin modal footers use shared panel actions", () => {
  const source = [
    readSource("../../panels/ModelPanel/tabs/ModelFormModal.tsx"),
    readSource("../../panels/ModelPanel/tabs/BatchCreateModal.tsx"),
  ].join("\n");

  expect(source).toMatch(/PanelFooterActions/);
  expect(source).toMatch(/<Button[\s>]/);
  expect(source).not.toMatch(/className="btn-(primary|secondary)[^"]*"/);
});

test("model admin modal form bodies use shared field primitives", () => {
  const modelForm = readSource(
    "../../panels/ModelPanel/tabs/ModelFormModal.tsx",
  );
  const batchCreate = readSource(
    "../../panels/ModelPanel/tabs/BatchCreateModal.tsx",
  );
  const source = [modelForm, batchCreate].join("\n");

  expect(source).toMatch(/import \{ Checkbox \}/);
  expect(source).toMatch(/import \{[\s\S]*Input[\s\S]*Select[\s\S]*Textarea/);
  expect(modelForm).toMatch(/<Select[\s\S]*formFallbackModel/);
  expect(modelForm).toMatch(/<Checkbox[\s\S]*checked=\{formSupportsVision\}/);
  expect(batchCreate).toMatch(/<Textarea[\s\S]*importJson/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/className="glass-input/);
  expect(source).not.toMatch(/<input[\s\S]*type="checkbox"/);
});

test("agent and model admin shells use shared buttons for header commands", () => {
  const source = [
    readSource("../../panels/AgentPanel/AgentConfigPanel.tsx"),
    readSource("../../panels/ModelPanel/ModelPanel.tsx"),
  ].join("\n");

  expect(source).toMatch(/import \{ Button \}/);
  expect(source).toMatch(/<Button[\s\S]*handleRefresh/);
  expect(source).not.toMatch(/className="btn-secondary[^"]*"/);
});

test("agent and model admin tab actions use shared buttons", () => {
  const sources = [
    readSource("../../panels/AgentPanel/tabs/GlobalAgentTab.tsx"),
    readSource("../../panels/AgentPanel/tabs/RolesAgentTab.tsx"),
    readSource("../../panels/ModelPanel/tabs/ModelConfigTab.tsx"),
    readSource("../../panels/ModelPanel/tabs/RolesModelTab.tsx"),
  ].join("\n");

  expect(sources).toMatch(/import \{[\s\S]*Button[\s\S]*\}/);
  expect(sources).toMatch(/<Button[\s\S]*agentConfig\.addModel/);
  expect(sources).toMatch(/<Button[\s\S]*common\.save/);
  expect(sources).not.toMatch(/className="btn-(primary|secondary)[^"]*"/);
});

test("global agent editor fields use shared field primitives", () => {
  const source = readSource("../../panels/AgentPanel/tabs/GlobalAgentTab.tsx");

  expect(source).toMatch(/import \{[\s\S]*Input[\s\S]*Textarea[\s\S]*\}/);
  expect(source).toMatch(/<Input[\s\S]*sort_order/);
  expect(source).toMatch(/<Input[\s\S]*agentConfig\.displayName/);
  expect(source).toMatch(/<Textarea[\s\S]*agentConfig\.displayDescription/);
  expect(source).not.toMatch(/className="glass-input/);
});

test("roles agent assignments use the shared checkbox primitive", () => {
  const source = readSource("../../panels/AgentPanel/tabs/RolesAgentTab.tsx");

  expect(source).toMatch(/import \{ Checkbox \}/);
  expect(source).toMatch(/<Checkbox[\s\S]*checked=\{isSelected\}/);
  expect(source).not.toMatch(/<input[\s\S]*type="checkbox"/);
});

test("channel panel generic controls use shared primitives", () => {
  const source = readSource("../../panels/ChannelPanel.tsx");

  expect(source).toMatch(/import \{[\s\S]*Button[\s\S]*Input[\s\S]*Select/);
  expect(source).toMatch(/<Select[\s\S]*field\.options/);
  expect(source).toMatch(/<Input[\s\S]*channel\.instanceNamePlaceholder/);
  expect(source).toMatch(/<Button[\s\S]*handleSave/);
  expect(source).toMatch(/<Button[\s\S]*handleDeleteClick/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/className="[^"]*glass-input/);
  expect(source).not.toMatch(/className="btn-(primary|secondary|danger)/);
});

test("settings panel generic controls use shared primitives", () => {
  const source = readSource("../../panels/SettingsPanel.tsx");

  expect(source).toMatch(
    /import \{[\s\S]*Button[\s\S]*Input[\s\S]*Select[\s\S]*Textarea/,
  );
  expect(source).toMatch(/<Select[\s\S]*CATEGORY_ORDER/);
  expect(source).toMatch(/<Select[\s\S]*DEFAULT_AGENT/);
  expect(source).toMatch(/setting\.type === "text"[\s\S]*<Textarea/);
  expect(source).toMatch(/<Input[\s\S]*setting\.type === "number"/);
  expect(source).toMatch(/<Button[\s\S]*handleExport/);
  expect(source).toMatch(/<Button[\s\S]*handleSave\(setting\)/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/className="btn-(primary|secondary|danger)/);
});

test("json schema editor uses shared primitives for generated controls", () => {
  const source = readSource("../../panels/JsonSchemaEditor.tsx");

  expect(source).toMatch(/import \{ Button, IconButton, Input, Select \}/);
  expect(source).toMatch(/<Select[\s\S]*field\.options/);
  expect(source).toMatch(/<Input[\s\S]*field\.placeholder/);
  expect(source).toMatch(/<IconButton[\s\S]*removeItem/);
  expect(source).toMatch(/<Button[\s\S]*JSON_SCHEMA_ADD_ITEM/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/<input[\s\S]*field\.placeholder/);
});

test("approval panel generated form fields use shared field primitives", () => {
  const source = readSource("../../panels/ApprovalPanel.tsx");

  expect(source).toMatch(/import \{[\s\S]*Input[\s\S]*Select[\s\S]*Textarea/);
  expect(source).toMatch(/case "text":[\s\S]*<Input/);
  expect(source).toMatch(/case "number":[\s\S]*<Input/);
  expect(source).toMatch(/case "textarea":[\s\S]*<Textarea/);
  expect(source).toMatch(/case "select":[\s\S]*<Select/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/<input[\s\S]*approval-input/);
  expect(source).not.toMatch(/<textarea[\s\S]*approval-input/);
});

test("scheduled task form uses shared primitives for generic form controls", () => {
  const source = readSource(
    "../../panels/ScheduledTaskPanel/TaskFormModal.tsx",
  );

  expect(source).toMatch(
    /import \{[\s\S]*Button[\s\S]*Input[\s\S]*PanelFooterActions[\s\S]*Select[\s\S]*Textarea/,
  );
  expect(source).toMatch(/<PanelFooterActions/);
  expect(source).toMatch(/<Button[\s\S]*handleSave/);
  expect(source).toMatch(/<Input[\s\S]*scheduledTask\.namePlaceholder/);
  expect(source).toMatch(
    /<Textarea[\s\S]*scheduledTask\.descriptionPlaceholder/,
  );
  expect(source).toMatch(/<Select[\s\S]*scheduledTask\.agentPlaceholder/);
  expect(source).toMatch(/<Select[\s\S]*scheduledTask\.modelPlaceholder/);
  expect(source).not.toMatch(/GlassSelect/);
  expect(source).not.toMatch(/className="btn-(primary|secondary)[^"]*"/);
  expect(source).not.toMatch(/<input[\s\S]*scheduled-task-input/);
  expect(source).not.toMatch(/<textarea[\s\S]*scheduled-task-input/);
});
