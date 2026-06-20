import test from "node:test";
import assert from "node:assert/strict";
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

  assert.match(source, /buildPluginRuntimeImpactSummary/);
  assert.match(source, /activeEntries: plugin\.executable/);
  assert.match(source, /blockedWhenDisabled/);
  assert.match(source, /resourceActions/);
  assert.match(source, /pluginRuntime\.contributionPreview\.disablePolicy/);
  assert.match(source, /pluginRuntime\.contributionPreview\.uninstallPolicy/);
  assert.match(source, /pluginRuntime\.runtimeSideEffect\.title/);
  assert.match(source, /plugin\.runtime_side_effect\.status/);
  assert.match(source, /sideEffectStatusClassName/);
  assert.match(source, /action \$\{value\}/);
  assert.match(source, /welcome surface \$\{value\}/);
  assert.match(source, /asset slot \$\{value\}/);
  assert.match(source, /i18n \$\{value\}/);
  assert.match(source, /AcceptanceMatrixOverview/);
  assert.match(source, /pluginRuntime\.acceptance\.title/);
  assert.match(source, /data\?\.runtime\.acceptance_matrix/);
  assert.match(source, /MigrationProgressOverview/);
  assert.match(source, /pluginRuntime\.progress\.title/);
  assert.match(source, /data\?\.runtime\.phase_progress/);
  assert.match(source, /pluginRuntime\.feedbackMigration\.title/);
  assert.match(source, /feedbackMigration\.gate_evidence/);
});

test("plugin runtime panel shows a first-screen ownership overview", () => {
  const source = readPanelSources();

  assert.match(source, /PluginOwnershipOverview/);
  assert.match(source, /pluginContributionLabels/);
  assert.match(source, /structuredFrontendDeclarationLabels/);
  assert.match(source, /legacyFrontendDeclarationLabels/);
  assert.match(source, /structuredFrontendContributionCount/);
  assert.match(source, /legacyFrontendContributionCount/);
  assert.match(source, /pluginRuntime\.ownership\.title/);
  assert.match(source, /API \$\{route\.prefix\}/);
  assert.match(source, /Agent \$\{agent\.id\}/);
  assert.match(source, /App Tab \$\{value\.path \|\| value\.tab\}/);
  assert.match(source, /App Panel \$\{value\.renderer\}/);
  assert.match(source, /Sidebar \$\{value\.path\}/);
  assert.match(source, /User Menu \$\{value\.path\}/);
  assert.match(source, /formatChatInputOptionLabel\(value, "Chat Option"\)/);
  assert.match(source, /suppresses core persona selector/);
  assert.match(source, /Message Action \$\{value\.id\}/);
  assert.match(source, /Mention \$\{value\.mode\}/);
  assert.match(source, /Welcome Surface \$\{value\.renderer\}/);
  assert.match(source, /Assistant Identity \$\{value\.resolver\}/);
  assert.match(source, /Agent Category \$\{value\.id\}/);
  assert.match(source, /Project Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /Session Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /Channel Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /Scheduled Task Option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /formatToolRendererContribution/);
  assert.match(source, /formatFileViewerContribution/);
  assert.match(source, /formatSkillImporterContribution/);
  assert.match(source, /formatChannelConnectorContribution/);
  assert.match(source, /Importer \$\{formatSkillImporterContribution\(value\)\}/);
  assert.match(source, /Connector \$\{formatChannelConnectorContribution\(value\)\}/);
  assert.match(source, /Asset Slot \$\{value\}/);
  assert.match(source, /Legacy UI/);
});

test("plugin runtime impact summary includes directory-declared UI and scoped option surfaces", () => {
  const source = readPanelSources();

  assert.match(source, /PluginContributionGroup/);
  assert.match(source, /pluginContributionGroups/);
  assert.match(source, /PluginContributionGroupGrid/);
  assert.match(source, /Backend/);
  assert.match(source, /App UI/);
  assert.match(source, /Chat UI/);
  assert.match(source, /Scoped Options/);
  assert.match(source, /Integrations/);
  assert.match(source, /Assets And Config/);
  assert.match(source, /frontendDeclarationLabels/);
  assert.match(source, /No directory-declared contributions/);
  assert.doesNotMatch(source, /Structured frontend declarations/);
  assert.doesNotMatch(source, /Legacy frontend compatibility/);
  assert.match(source, /app tab \$\{value\.path \|\| value\.tab\}/);
  assert.match(source, /app panel \$\{value\.renderer\}/);
  assert.match(source, /sidebar \$\{value\.path\}/);
  assert.match(source, /user menu \$\{value\.path\}/);
  assert.match(source, /formatChatInputOptionLabel\(value, "chat option"\)/);
  assert.match(source, /suppresses_core_persona_selector/);
  assert.match(source, /chat panel \$\{value\.renderer\}/);
  assert.match(source, /mention \$\{value\.mode\}/);
  assert.match(source, /welcome surface \$\{value\.renderer\}/);
  assert.match(source, /project option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /session option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /channel option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /scheduled task option \$\{plugin\.plugin_id\}\.\$\{value\.key\}/);
  assert.match(source, /assistant identity \$\{value\.resolver\}/);
  assert.match(source, /agent category \$\{value\.id\}/);
  assert.match(source, /agent \$\{agent\.id\}/);
  assert.match(source, /structuredFrontendCount/);
  assert.match(source, /legacyFrontendCount/);
  assert.match(source, /plugin\.frontend\.app_tabs\.length/);
  assert.match(source, /plugin\.frontend\.chat_input_options\.length/);
  assert.match(source, /plugin\.frontend\.welcome_surfaces\.length/);
  assert.match(source, /plugin\.frontend\.project_options\.length/);
  assert.match(source, /plugin\.frontend\.session_options\.length/);
  assert.match(source, /plugin\.frontend\.channel_options/);
  assert.match(source, /plugin\.frontend\.scheduled_task_options\.length/);
  assert.match(source, /plugin\.agents\.length/);
});

test("first-party frontend package manifests use structured declarations instead of legacy route fields", () => {
  for (const relativePath of [
    "../../../../../plugins/system/feedback/frontend/plugin.json",
    "../../../../../plugins/system/agent_team/frontend/plugin.json",
    "../../../../../plugins/system/usage_reports/frontend/plugin.json",
  ]) {
    const manifest = JSON.parse(readFileSync(resolve(__dirname, relativePath), "utf8"));
    const frontend = manifest.frontend ?? manifest;

    assert.equal(frontend.routes, undefined, `${relativePath} must not declare legacy routes`);
    assert.equal(frontend.panels, undefined, `${relativePath} must not declare legacy panels`);
    assert.equal(frontend.nav_items, undefined, `${relativePath} must not declare legacy nav_items`);
    assert.ok(Array.isArray(frontend.app_tabs), `${relativePath} declares app_tabs`);
    assert.ok(Array.isArray(frontend.app_panels), `${relativePath} declares app_panels`);
  }
});

test("plugin runtime panel keeps plugin rows compact and truly collapsible", () => {
  const source = readPanelSources();

  assert.doesNotMatch(source, /setExpandedPluginId\(plugins\[0\]\.plugin_id\)/);
  assert.match(source, /aria-expanded=\{isExpanded\}/);
  assert.match(source, /pluginRuntime\.diagnostics\.title/);
  assert.match(source, /showDiagnostics/);
  assert.match(source, /CompactStat label=\{t\("pluginRuntime\.metrics\.settings"\)\}/);
  assert.match(source, /plugin\.resource_types\.setting/);
  assert.match(source, /space-y-2/);
});

test("plugin runtime panel exposes export import and protected uninstall controls", () => {
  const source = readPanelSources();

  assert.match(source, /pluginRuntime\.actions\.export/);
  assert.match(source, /pluginRuntime\.actions\.import/);
  assert.match(source, /pluginRuntime\.actions\.uninstall/);
  assert.match(source, /plugin\.install_type/);
  assert.match(source, /plugin\.uninstallable/);
  assert.match(source, /pluginRuntime\.uninstall\.protected/);
  assert.match(source, /pluginRuntime\.uninstall\.confirm/);
});

test("plugin runtime panel surfaces plugin data templates", () => {
  const source = readPanelSources();
  const typeSource = readFileSync(
    resolve(__dirname, "../../../types/pluginRuntime.ts"),
    "utf8",
  );

  assert.match(typeSource, /data_template: string/);
  assert.match(source, /plugin-data-template/);
  assert.match(source, /packageLayout\.data_template/);
  assert.match(source, /dataTemplate\.template/);
  assert.match(source, /dataTemplate\.file_count/);
  assert.match(source, /dataTemplate\.files\.slice/);
  assert.match(source, /dataTemplate\.total_bytes/);
  assert.match(source, /config\/current\.json/);
  assert.match(source, /config\/defaults\.json/);
  assert.match(source, /state\/audit\.jsonl/);
});

test("plugin runtime panel exposes package manifest authority", () => {
  const source = readPanelSources();

  assert.match(source, /manifest_authority/);
  assert.match(source, /static_fallback_used/);
  assert.match(source, /static_fallback_fields/);
  assert.match(source, /authority \{packageInfo\.manifest_authority/);
  assert.match(source, /fallback \{packageInfo\.static_fallback_used/);
});

test("plugin runtime panel exposes package data export policy", () => {
  const source = readPanelSources();

  assert.match(source, /data export policy/);
  assert.match(source, /runtime_data_in_archive/);
  assert.match(source, /snapshot_metadata_in_export/);
  assert.match(source, /default_retention/);
  assert.match(source, /sensitive_settings_included/);
});

test("plugin runtime panel exposes dry-run package data policy", () => {
  const source = readPanelSources();

  assert.match(source, /package_data_policy/);
  assert.match(source, /package folder \{dryRun\.package_data_policy\.package_folder_action/);
  assert.match(source, /plugin-data \{dryRun\.package_data_policy\.plugin_data_folder_action/);
  assert.match(source, /data config \{dryRun\.package_data_policy\.plugin_data_config_action/);
  assert.match(source, /data storage \{dryRun\.package_data_policy\.plugin_data_storage_action/);
  assert.match(source, /runtime data delete/);
  assert.match(source, /sensitive settings delete/);
});

test("plugin runtime panel exposes archived package restore controls", () => {
  const source = readPanelSources();

  assert.match(source, /archivedPackages/);
  assert.match(source, /Archived packages/);
  assert.match(source, /restoreArchivedPackage/);
  assert.match(source, /packageRestoreResult/);
  assert.match(source, /lastUninstallResult/);
  assert.match(source, /plugin-data \{lastUninstallResult\.plugin_data_retained/);
  assert.match(source, /Restore/);
});

test("plugin runtime imports notify contribution consumers after runtime mutations", () => {
  const hookSource = readFileSync(
    resolve(__dirname, "../../../hooks/usePluginRuntime.ts"),
    "utf8",
  );

  assert.match(hookSource, /await pluginRuntimeApi\.importPlugin\(payload, restoreState\);[\s\S]*dispatchPluginRuntimeUpdated\(\);/);
  assert.match(hookSource, /await pluginRuntimeApi\.importPackage\(sourcePath, dryRun\);[\s\S]*if \(!dryRun\) \{\s*dispatchPluginRuntimeUpdated\(\);\s*\}/);
});

test("plugin runtime panel exposes package integrity evidence", () => {
  const source = readPanelSources();

  assert.match(source, /package_sha256/);
  assert.match(source, /signature_status/);
  assert.match(source, /sha256 \{packageImportResult\.integrity\.package_sha256/);
  assert.match(source, /lastUninstallResult\.package_integrity/);
  assert.match(source, /packageRestoreResult\.integrity\.package_sha256/);
  assert.match(source, /item\.integrity\.package_sha256/);
  assert.match(source, /supports_package_integrity/);
  assert.match(source, /requires_signed_user_installed_enable/);
  assert.match(source, /unsigned plugin packages stay disabled/);
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

  assert.match(panelSource, /package review/);
  assert.match(panelSource, /Review hash/);
  assert.match(panelSource, /active_for_current_package/);
  assert.match(panelSource, /packageReviewByPlugin/);
  assert.match(hookSource, /getPackageReview/);
  assert.match(hookSource, /reviewPluginPackage/);
  assert.match(apiSource, /package-review/);
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

  assert.match(panelSource, /Reset data config/);
  assert.match(panelSource, /backup_count/);
  assert.match(panelSource, /last_backup_path/);
  assert.match(panelSource, /onResetPluginData/);
  assert.match(hookSource, /resetPluginData/);
  assert.match(apiSource, /data\/reset/);
});

test("plugin runtime panel exposes plugin package dependencies", () => {
  const panelSource = readPanelSources();
  const typeSource = readFileSync(
    resolve(__dirname, "../../../types/pluginRuntime.ts"),
    "utf8",
  );

  assert.match(typeSource, /depends_on: string\[\]/);
  assert.match(panelSource, /dependencies/);
  assert.match(panelSource, /plugin\.depends_on \?\? \[\]/);
  assert.match(panelSource, /Deps/);
});
