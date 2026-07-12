import { readFileSync } from "node:fs";
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

  expect(source).not.toMatch(/const\s+\w+\s*=\s*import\.meta\.glob/);
  expect(source).toMatch(/import\.meta\.glob<PluginLocaleResource>\(\s*\[/);
  expect(source).toMatch(/"\.\.\/\.\.\/\.\.\/plugins\/system\/\*\/frontend\/locales\/\*\.json"/);
  expect(source).toMatch(/"\.\.\/\.\.\/\.\.\/plugins\/preinstalled\/\*\/frontend\/locales\/\*\.json"/);
  expect(source).toMatch(/"\.\.\/\.\.\/\.\.\/plugin-data\/\*\/frontend\/locales\/\*\.json"/);
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

  expect(resources.en).toEqual({
    samplePlugin: { nav: { label: "Sample" } },
  });
  expect(resources.zh).toEqual({
    samplePlugin: {
      nav: { label: "Sample zh" },
      editor: { graph: { title: "Editor zh" } },
    },
  });
  expect(resources.fr).toBe(undefined);
});

test("plugin locale resources override base locale keys while preserving siblings", () => {
  expect(mergeLocaleResource(
      {
        samplePlugin: {
          nav: { label: "Base" },
          chat: { selectItem: "Sample" },
        },
      },
      { samplePlugin: { nav: { label: "Plugin" } } },
    )).toEqual({
      samplePlugin: {
        nav: { label: "Plugin" },
        chat: { selectItem: "Sample" },
      },
    });
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

  expect(en.samplePlugin.editor.route.listTitle).toBe("Supplemental samples");
  expect(en.samplePlugin.editor.route.listSubtitle).toBe("Bundled subtitle");
  expect(zh.samplePlugin.editor.route.listTitle).toBe("Supplemental samples zh");
});
