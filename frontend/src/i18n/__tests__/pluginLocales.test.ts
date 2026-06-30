import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  collectPluginLocaleResources,
  mergePluginLocaleResourceSets,
  mergeLocaleResource,
} from "../pluginLocales";

const currentDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(currentDir, "../../../..");

test("plugin locale loader uses a direct literal glob for Vite production builds", () => {
  const source = readFileSync(resolve(currentDir, "../pluginLocales.ts"), "utf8");

  assert.doesNotMatch(source, /const\s+\w+\s*=\s*import\.meta\.glob/);
  assert.match(source, /import\.meta\.glob<PluginLocaleResource>\(\s*\[/);
  assert.match(source, /"\.\.\/\.\.\/\.\.\/plugins\/system\/\*\/frontend\/locales\/\*\.json"/);
  assert.match(source, /"\.\.\/\.\.\/\.\.\/plugins\/preinstalled\/\*\/frontend\/locales\/\*\.json"/);
  assert.match(source, /"\.\.\/\.\.\/\.\.\/plugin-data\/\*\/frontend\/locales\/\*\.json"/);
});

test("plugin locale resources are collected by language and deeply merged", () => {
  const resources = collectPluginLocaleResources({
    "../../../plugins/system/workflow/frontend/locales/en.json": {
      workflowPlugin: { nav: { label: "Workflows" } },
    },
    "../../../plugins/system/workflow/frontend/locales/zh.json": {
      default: {
        workflowPlugin: {
          nav: { label: "工作流" },
          editor: { graph: { title: "图编辑器" } },
        },
      },
    },
    "../../../plugins/system/workflow/frontend/locales/fr.json": {
      workflowPlugin: { nav: { label: "Flux" } },
    },
    "../../../plugins/system/workflow/frontend/not-locales/en.json": {
      workflowPlugin: { nav: { label: "Ignored" } },
    },
  });

  assert.deepEqual(resources.en, {
    workflowPlugin: { nav: { label: "Workflows" } },
  });
  assert.deepEqual(resources.zh, {
    workflowPlugin: {
      nav: { label: "工作流" },
      editor: { graph: { title: "图编辑器" } },
    },
  });
  assert.equal(resources.fr, undefined);
});

test("plugin locale resources override base locale keys while preserving siblings", () => {
  assert.deepEqual(
    mergeLocaleResource(
      { workflowPlugin: { nav: { label: "Base" }, chat: { selectWorkflow: "Workflow" } } },
      { workflowPlugin: { nav: { label: "Plugin" } } },
    ),
    {
      workflowPlugin: {
        nav: { label: "Plugin" },
        chat: { selectWorkflow: "Workflow" },
      },
    },
  );
});

test("plugin-data supplemental locale resources override bundled plugin defaults", () => {
  const bundled = collectPluginLocaleResources({
    "../../../plugins/system/workflow/frontend/locales/en.json": {
      workflowPlugin: {
        editor: {
          route: {
            listTitle: "Workflows",
            listSubtitle: "Bundled subtitle",
          },
        },
      },
    },
  });
  const supplemental = collectPluginLocaleResources({
    "../../../plugin-data/workflow/frontend/locales/en.json": {
      workflowPlugin: {
        editor: {
          route: {
            listTitle: "Supplemental workflows",
          },
        },
      },
    },
    "../../../plugin-data/workflow/frontend/locales/zh.json": {
      workflowPlugin: {
        editor: {
          route: {
            listTitle: "工作流",
          },
        },
      },
    },
  });

  const resources = mergePluginLocaleResourceSets(bundled, supplemental);
  const en = resources.en as {
    workflowPlugin: { editor: { route: { listTitle: string; listSubtitle: string } } };
  };
  const zh = resources.zh as {
    workflowPlugin: { editor: { route: { listTitle: string } } };
  };

  assert.equal(en.workflowPlugin.editor.route.listTitle, "Supplemental workflows");
  assert.equal(en.workflowPlugin.editor.route.listSubtitle, "Bundled subtitle");
  assert.equal(zh.workflowPlugin.editor.route.listTitle, "工作流");
});

test("workflow plugin ships a default locale and supplemental locales for every other app language", () => {
  const pluginLocalesDir = resolve(
    repoRoot,
    "plugins",
    "system",
    "workflow",
    "frontend",
    "locales",
  );
  const pluginDataLocalesDir = resolve(
    repoRoot,
    "plugin-data",
    "workflow",
    "frontend",
    "locales",
  );
  const localePath = (language: string) =>
    language === "en"
      ? resolve(pluginLocalesDir, "en.json")
      : resolve(pluginDataLocalesDir, `${language}.json`);

  for (const language of ["en", "zh", "ja", "ko", "ru"]) {
    const locale = JSON.parse(
      readFileSync(localePath(language), "utf8"),
    );
    assert.equal(typeof locale.workflowPlugin.nav.label, "string");
    assert.equal(typeof locale.workflowPlugin.editor.graph.title, "string");
    assert.equal(typeof locale.workflowPlugin.editor.route.listTitle, "string");
    assert.equal(typeof locale.workflowPlugin.editor.toolbar.newWorkflow, "string");
    assert.equal(typeof locale.workflowPlugin.editor.inventory.noWorkflows, "string");
    assert.equal(typeof locale.workflowPlugin.editor.import.dryRun, "string");
    assert.equal(typeof locale.workflowPlugin.editor.delete.action, "string");
    assert.equal(typeof locale.workflowPlugin.editor.run.workflowInterface, "string");
    assert.equal(typeof locale.workflowPlugin.editor.run.runVersion, "string");
    assert.equal(typeof locale.workflowPlugin.editor.toast.workflowDeleted, "string");
    assert.equal(typeof locale.workflowPlugin.editor.toast.workflowImported, "string");
    assert.equal(typeof locale.workflowPlugin.editor.toast.workflowRunCompleted, "string");
    assert.equal(typeof locale.workflowPlugin.editor.run.outputContractStatus.satisfied, "string");
    assert.equal(typeof locale.workflowPlugin.plugin.name, "string");
    assert.equal(typeof locale.workflowPlugin.plugin.description, "string");
    assert.equal(typeof locale.workflowPlugin.defaults.importedWorkflowName, "string");
    assert.equal(typeof locale.workflowPlugin.defaults.entryMessageDescription, "string");
    assert.equal(typeof locale.workflowPlugin.validation.invalidJson, "string");
    assert.equal(typeof locale.workflowPlugin.validation.inputObjectRequired, "string");
    assert.equal(typeof locale.pluginSettings.workflow.DEFAULT_MODEL.label, "string");
    assert.equal(typeof locale.pluginSettings.workflow.DEFAULT_MODEL.description, "string");
    assert.equal(typeof locale.pluginSettings.workflow.RUN_LOG_RETENTION_DAYS.description, "string");
  }
});
