import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const readPanelSources = () =>
  [
    "../PluginRuntimePanel.tsx",
    "../pluginRuntimePanelUtils.ts",
    "../pluginRuntimeImpactSummary.ts",
  ]
    .map((relativePath) => readFileSync(resolve(__dirname, relativePath), "utf8"))
    .join("\n");

test("plugin runtime panel exposes operator-facing impact sections", () => {
  const source = readPanelSources();

  expect(source).toMatch(/buildPluginRuntimeImpactSummary/);
  expect(source).toMatch(/activeEntries: plugin\.executable/);
  expect(source).toMatch(/blockedWhenDisabled/);
  expect(source).toMatch(/resourceActions/);
  expect(source).toMatch(/pluginRuntime\.contributionPreview\.disablePolicy/);
  expect(source).toMatch(/pluginRuntime\.contributionPreview\.uninstallPolicy/);
  expect(source).toMatch(/pluginRuntime\.runtimeSideEffect\.title/);
  expect(source).toMatch(/plugin\.runtime_side_effect\.status/);
  expect(source).toMatch(/sideEffectStatusClassName/);
  expect(source).toMatch(/action \$\{value\}/);
  expect(source).toMatch(/welcome surface \$\{value\}/);
  expect(source).toMatch(/asset slot \$\{value\}/);
  expect(source).toMatch(/i18n \$\{value\}/);
  expect(source).toMatch(/AcceptanceMatrixOverview/);
  expect(source).toMatch(/pluginRuntime\.acceptance\.title/);
  expect(source).toMatch(/data\?\.runtime\.acceptance_matrix/);
  expect(source).toMatch(/MigrationProgressOverview/);
  expect(source).toMatch(/pluginRuntime\.progress\.title/);
  expect(source).toMatch(/data\?\.runtime\.phase_progress/);
  expect(source).toMatch(/pluginRuntime\.feedbackMigration\.title/);
  expect(source).toMatch(/feedbackMigration\.gate_evidence/);
});

test("plugin runtime panel shows a first-screen ownership overview", () => {
  const source = readPanelSources();

  expect(source).toMatch(/PluginOwnershipOverview/);
  expect(source).toMatch(/pluginContributionLabels/);
  expect(source).toMatch(/structuredFrontendDeclarationLabels/);
  expect(source).toMatch(/legacyFrontendDeclarationLabels/);
  expect(source).toMatch(/structuredFrontendContributionCount/);
  expect(source).toMatch(/legacyFrontendContributionCount/);
  expect(source).toMatch(/pluginRuntime\.ownership\.title/);
  expect(source).toMatch(/API \$\{route\.prefix\}/);
  expect(source).toMatch(/Agent \$\{agent\.id\}/);
  expect(source).toMatch(/App Tab \$\{value\.path \|\| value\.tab\}/);
  expect(source).toMatch(/App Panel \$\{value\.renderer\}/);
  expect(source).toMatch(/Sidebar \$\{value\.path\}/);
  expect(source).toMatch(/User Menu \$\{value\.path\}/);
  expect(source).toMatch(/formatChatInputOptionLabel\(value, "Chat Option"\)/);
  expect(source).toMatch(/suppresses core persona selector/);
  expect(source).toMatch(/Message Action \$\{value\.id\}/);
  expect(source).toMatch(/Mention \$\{value\.mode\}/);
  expect(source).toMatch(/Welcome Surface \$\{value\.renderer\}/);
  expect(source).toMatch(/Assistant Identity \$\{value\.resolver\}/);
  expect(source).toMatch(/Agent Category \$\{value\.id\}/);
  expect(source).toMatch(/Project Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/Session Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/Channel Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/Scheduled Task Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/formatToolRendererContribution/);
  expect(source).toMatch(/formatFileViewerContribution/);
  expect(source).toMatch(/formatSkillImporterContribution/);
  expect(source).toMatch(/formatChannelConnectorContribution/);
  expect(source).toMatch(/Importer \$\{formatSkillImporterContribution\(value\)\}/);
  expect(source).toMatch(/Connector \$\{formatChannelConnectorContribution\(value\)\}/);
  expect(source).toMatch(/Asset Slot \$\{value\}/);
  expect(source).toMatch(/Legacy UI/);
});

test("plugin runtime impact summary includes directory-declared UI and scoped option surfaces", () => {
  const source = readPanelSources();

  expect(source).toMatch(/PluginContributionGroup/);
  expect(source).toMatch(/pluginContributionGroups/);
  expect(source).toMatch(/PluginContributionGroupGrid/);
  expect(source).toMatch(/Backend/);
  expect(source).toMatch(/App UI/);
  expect(source).toMatch(/Chat UI/);
  expect(source).toMatch(/Scoped Options/);
  expect(source).toMatch(/Integrations/);
  expect(source).toMatch(/Assets And Config/);
  expect(source).toMatch(/frontendDeclarationLabels/);
  expect(source).toMatch(/No directory-declared contributions/);
  expect(source).not.toMatch(/Structured frontend declarations/);
  expect(source).not.toMatch(/Legacy frontend compatibility/);
  expect(source).toMatch(/app tab \$\{value\.path \|\| value\.tab\}/);
  expect(source).toMatch(/app panel \$\{value\.renderer\}/);
  expect(source).toMatch(/sidebar \$\{value\.path\}/);
  expect(source).toMatch(/user menu \$\{value\.path\}/);
  expect(source).toMatch(/formatChatInputOptionLabel\(value, "chat option"\)/);
  expect(source).toMatch(/suppresses_core_persona_selector/);
  expect(source).toMatch(/chat panel \$\{value\.renderer\}/);
  expect(source).toMatch(/mention \$\{value\.mode\}/);
  expect(source).toMatch(/welcome surface \$\{value\.renderer\}/);
  expect(source).toMatch(/project option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/session option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/channel option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/scheduled task option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  expect(source).toMatch(/assistant identity \$\{value\.resolver\}/);
  expect(source).toMatch(/agent category \$\{value\.id\}/);
  expect(source).toMatch(/agent \$\{agent\.id\}/);
  expect(source).toMatch(/structuredFrontendCount/);
  expect(source).toMatch(/legacyFrontendCount/);
  expect(source).toMatch(/plugin\.frontend\.app_tabs\.length/);
  expect(source).toMatch(/plugin\.frontend\.chat_input_options\.length/);
  expect(source).toMatch(/plugin\.frontend\.welcome_surfaces\.length/);
  expect(source).toMatch(/plugin\.frontend\.project_options\.length/);
  expect(source).toMatch(/plugin\.frontend\.session_options\.length/);
  expect(source).toMatch(/plugin\.frontend\.channel_options/);
  expect(source).toMatch(/plugin\.frontend\.scheduled_task_options\.length/);
  expect(source).toMatch(/plugin\.agents\.length/);
});

test("first-party frontend package manifests use structured declarations instead of legacy route fields", () => {
  for (const relativePath of [
    "../../../../../plugins/system/feedback/frontend/plugin.json",
    "../../../../../plugins/system/agent_team/frontend/plugin.json",
    "../../../../../plugins/system/usage_reports/frontend/plugin.json",
  ]) {
    const manifest = JSON.parse(readFileSync(resolve(__dirname, relativePath), "utf8"));
    const frontend = manifest.frontend ?? manifest;

    expect(frontend.routes).toBe(undefined);
    expect(frontend.panels).toBe(undefined);
    expect(frontend.nav_items).toBe(undefined);
    expect(Array.isArray(frontend.app_tabs)).toBeTruthy();
    expect(Array.isArray(frontend.app_panels)).toBeTruthy();
  }
});

test("plugin runtime panel keeps plugin rows compact and truly collapsible", () => {
  const source = readPanelSources();

  expect(source).not.toMatch(/setExpandedPluginId\(plugins\[0\]\.plugin_id\)/);
  expect(source).toMatch(/aria-expanded=\{isExpanded\}/);
  expect(source).toMatch(/pluginRuntime\.diagnostics\.title/);
  expect(source).toMatch(/showDiagnostics/);
  expect(source).toMatch(/CompactStat label=\{t\("pluginRuntime\.metrics\.settings"\)\}/);
  expect(source).toMatch(/plugin\.resource_types\.setting/);
  expect(source).toMatch(/space-y-2/);
});

test("plugin runtime panel exposes export import and protected uninstall controls", () => {
  const source = readPanelSources();

  expect(source).toMatch(/pluginRuntime\.actions\.export/);
  expect(source).toMatch(/pluginRuntime\.actions\.import/);
  expect(source).toMatch(/pluginRuntime\.actions\.uninstall/);
  expect(source).toMatch(/plugin\.install_type/);
  expect(source).toMatch(/plugin\.uninstallable/);
  expect(source).toMatch(/pluginRuntime\.uninstall\.protected/);
  expect(source).toMatch(/pluginRuntime\.uninstall\.confirm/);
});

test("plugin runtime panel surfaces plugin data templates", () => {
  const source = readPanelSources();
  const typeSource = readFileSync(
    resolve(__dirname, "../../../types/pluginRuntime.ts"),
    "utf8",
  );

  expect(typeSource).toMatch(/data_template: string/);
  expect(source).toMatch(/plugin-data-template/);
  expect(source).toMatch(/packageLayout\.data_template/);
  expect(source).toMatch(/dataTemplate\.template/);
  expect(source).toMatch(/dataTemplate\.file_count/);
  expect(source).toMatch(/dataTemplate\.files\.slice/);
  expect(source).toMatch(/dataTemplate\.total_bytes/);
  expect(source).toMatch(/config\/current\.json/);
  expect(source).toMatch(/config\/defaults\.json/);
  expect(source).toMatch(/state\/audit\.jsonl/);
});

test("plugin runtime panel exposes package manifest authority", () => {
  const source = readPanelSources();

  expect(source).toMatch(/manifest_authority/);
  expect(source).toMatch(/static_fallback_used/);
  expect(source).toMatch(/static_fallback_fields/);
  expect(source).toMatch(/authority \{packageInfo\.manifest_authority/);
  expect(source).toMatch(/fallback \{packageInfo\.static_fallback_used/);
});

test("plugin runtime panel exposes package data export policy", () => {
  const source = readPanelSources();

  expect(source).toMatch(/data export policy/);
  expect(source).toMatch(/runtime_data_in_archive/);
  expect(source).toMatch(/snapshot_metadata_in_export/);
  expect(source).toMatch(/default_retention/);
  expect(source).toMatch(/sensitive_settings_included/);
});

test("plugin runtime panel exposes dry-run package data policy", () => {
  const source = readPanelSources();

  expect(source).toMatch(/package_data_policy/);
  expect(source).toMatch(/package folder \{dryRun\.package_data_policy\.package_folder_action/);
  expect(source).toMatch(/plugin-data \{dryRun\.package_data_policy\.plugin_data_folder_action/);
  expect(source).toMatch(/data config \{dryRun\.package_data_policy\.plugin_data_config_action/);
  expect(source).toMatch(/data storage \{dryRun\.package_data_policy\.plugin_data_storage_action/);
  expect(source).toMatch(/runtime data delete/);
  expect(source).toMatch(/sensitive settings delete/);
});

test("plugin runtime panel exposes archived package restore controls", () => {
  const source = readPanelSources();

  expect(source).toMatch(/archivedPackages/);
  expect(source).toMatch(/Archived packages/);
  expect(source).toMatch(/restoreArchivedPackage/);
  expect(source).toMatch(/packageRestoreResult/);
  expect(source).toMatch(/lastUninstallResult/);
  expect(source).toMatch(/plugin-data \{lastUninstallResult\.plugin_data_retained/);
  expect(source).toMatch(/Restore/);
});

test("plugin runtime imports notify contribution consumers after runtime mutations", () => {
  const hookSource = readFileSync(
    resolve(__dirname, "../../../hooks/usePluginRuntime.ts"),
    "utf8",
  );

  expect(hookSource).toMatch(/await pluginRuntimeApi\.importPlugin\(payload, restoreState\);[\s\S]*dispatchPluginRuntimeUpdated\(\);/);
  expect(hookSource).toMatch(/await pluginRuntimeApi\.importPackage\(sourcePath, dryRun\);[\s\S]*if \(!dryRun\) \{\s*dispatchPluginRuntimeUpdated\(\);\s*\}/);
});

test("plugin runtime panel exposes package integrity evidence", () => {
  const source = readPanelSources();

  expect(source).toMatch(/package_sha256/);
  expect(source).toMatch(/signature_status/);
  expect(source).toMatch(/sha256 \{packageImportResult\.integrity\.package_sha256/);
  expect(source).toMatch(/lastUninstallResult\.package_integrity/);
  expect(source).toMatch(/packageRestoreResult\.integrity\.package_sha256/);
  expect(source).toMatch(/item\.integrity\.package_sha256/);
  expect(source).toMatch(/supports_package_integrity/);
  expect(source).toMatch(/requires_signed_user_installed_enable/);
  expect(source).toMatch(/unsigned plugin packages stay disabled/);
});

test("plugin runtime panel exposes local package hash review controls", () => {
  const panelSource = readPanelSources();
  const hookSource = readFileSync(
    resolve(__dirname, "../../../hooks/usePluginRuntime.ts"),
    "utf8",
  );
  const apiSource = readFileSync(
    resolve(__dirname, "../../../services/api/pluginRuntime.ts"),
    "utf8",
  );

  expect(panelSource).toMatch(/package review/);
  expect(panelSource).toMatch(/Review hash/);
  expect(panelSource).toMatch(/active_for_current_package/);
  expect(panelSource).toMatch(/packageReviewByPlugin/);
  expect(hookSource).toMatch(/getPackageReview/);
  expect(hookSource).toMatch(/reviewPluginPackage/);
  expect(apiSource).toMatch(/package-review/);
});

test("plugin runtime panel exposes plugin-data reset and backup evidence", () => {
  const panelSource = readPanelSources();
  const hookSource = readFileSync(
    resolve(__dirname, "../../../hooks/usePluginRuntime.ts"),
    "utf8",
  );
  const apiSource = readFileSync(
    resolve(__dirname, "../../../services/api/pluginRuntime.ts"),
    "utf8",
  );

  expect(panelSource).toMatch(/Reset data config/);
  expect(panelSource).toMatch(/backup_count/);
  expect(panelSource).toMatch(/last_backup_path/);
  expect(panelSource).toMatch(/onResetPluginData/);
  expect(hookSource).toMatch(/resetPluginData/);
  expect(apiSource).toMatch(/data\/reset/);
});

test("plugin runtime panel exposes plugin package dependencies", () => {
  const panelSource = readPanelSources();
  const typeSource = readFileSync(
    resolve(__dirname, "../../../types/pluginRuntime.ts"),
    "utf8",
  );

  expect(typeSource).toMatch(/depends_on: string\[\]/);
  expect(panelSource).toMatch(/dependencies/);
  expect(panelSource).toMatch(/plugin\.depends_on \?\? \[\]/);
  expect(panelSource).toMatch(/Deps/);
});
