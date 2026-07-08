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
    "../../../plugins/system/sample_plugin/frontend/locales/en.json": {
      samplePlugin: { nav: { label: "Sample" } },
    },
    "../../../plugins/system/sample_plugin/frontend/locales/zh.json": {
      default: {
        samplePlugin: {
          nav: { label: "Sample zh" },
          editor: { graph: { title: "Editor zh" } },
        },
      },
    },
    "../../../plugins/system/sample_plugin/frontend/locales/fr.json": {
      samplePlugin: { nav: { label: "Sample fr" } },
    },
    "../../../plugins/system/sample_plugin/frontend/not-locales/en.json": {
      samplePlugin: { nav: { label: "Ignored" } },
    },
  });

  assert.deepEqual(resources.en, {
    samplePlugin: { nav: { label: "Sample" } },
  });
  assert.deepEqual(resources.zh, {
    samplePlugin: {
      nav: { label: "Sample zh" },
      editor: { graph: { title: "Editor zh" } },
    },
  });
  assert.equal(resources.fr, undefined);
});

test("plugin locale resources override base locale keys while preserving siblings", () => {
  assert.deepEqual(
    mergeLocaleResource(
      {
        samplePlugin: {
          nav: { label: "Base" },
          chat: { selectItem: "Sample" },
        },
      },
      { samplePlugin: { nav: { label: "Plugin" } } },
    ),
    {
      samplePlugin: {
        nav: { label: "Plugin" },
        chat: { selectItem: "Sample" },
      },
    },
  );
});

test("plugin-data supplemental locale resources override bundled plugin defaults", () => {
  const bundled = collectPluginLocaleResources({
    "../../../plugins/system/sample_plugin/frontend/locales/en.json": {
      samplePlugin: {
        editor: {
          route: {
            listTitle: "Samples",
            listSubtitle: "Bundled subtitle",
          },
        },
      },
    },
  });
  const supplemental = collectPluginLocaleResources({
    "../../../plugin-data/sample_plugin/frontend/locales/en.json": {
      samplePlugin: {
        editor: {
          route: {
            listTitle: "Supplemental samples",
          },
        },
      },
    },
    "../../../plugin-data/sample_plugin/frontend/locales/zh.json": {
      samplePlugin: {
        editor: {
          route: {
            listTitle: "Supplemental samples zh",
          },
        },
      },
    },
  });

  const resources = mergePluginLocaleResourceSets(bundled, supplemental);
  const en = resources.en as {
    samplePlugin: { editor: { route: { listTitle: string; listSubtitle: string } } };
  };
  const zh = resources.zh as {
    samplePlugin: { editor: { route: { listTitle: string } } };
  };

  assert.equal(en.samplePlugin.editor.route.listTitle, "Supplemental samples");
  assert.equal(en.samplePlugin.editor.route.listSubtitle, "Bundled subtitle");
  assert.equal(zh.samplePlugin.editor.route.listTitle, "Supplemental samples zh");
});
