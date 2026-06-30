import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPluginAssetUrl,
  findPluginAssetSlot,
  hasPluginAssetSlot,
  listPluginAssetSlots,
  PLUGIN_FRONTEND_ASSET_SCHEMA,
} from "../pluginAssetSlots";
import type { PluginRuntimeContributionState } from "../coreContributions";

function runtimePlugin(
  overrides: Partial<PluginRuntimeContributionState> = {},
): PluginRuntimeContributionState {
  return {
    plugin_id: "advanced_file_viewers",
    enabled: true,
    executable: true,
    status: "enabled",
    package: {
      frontend_assets: {
        plugin_id: "advanced_file_viewers",
        asset_schema: PLUGIN_FRONTEND_ASSET_SCHEMA,
        slots: ["file_viewer"],
        assets: ["viewer.js"],
        phase: "static_asset_mount_placeholder",
      },
    },
    ...overrides,
  };
}

test("plugin asset slot registry lists enabled runtime slots", () => {
  const entries = listPluginAssetSlots([runtimePlugin()]);

  assert.deepEqual(entries, [
    {
      id: "advanced_file_viewers:file_viewer",
      pluginId: "advanced_file_viewers",
      slot: "file_viewer",
      assetSchema: PLUGIN_FRONTEND_ASSET_SCHEMA,
      assets: ["viewer.js"],
      mountPath: "/plugin-assets/advanced_file_viewers/",
    },
  ]);
  assert.equal(hasPluginAssetSlot("file_viewer", [runtimePlugin()]), true);
  assert.equal(findPluginAssetSlot("file_viewer", [runtimePlugin()])?.pluginId, "advanced_file_viewers");
});

test("plugin asset slot registry filters disabled mismatched or unsupported bundles", () => {
  assert.deepEqual(
    listPluginAssetSlots([
      runtimePlugin({ enabled: false, executable: false, status: "disabled" }),
    ]),
    [],
  );
  assert.deepEqual(
    listPluginAssetSlots([
      runtimePlugin({
        package: {
          frontend_assets: {
            plugin_id: "other_plugin",
            asset_schema: PLUGIN_FRONTEND_ASSET_SCHEMA,
            slots: ["file_viewer"],
            assets: ["viewer.js"],
            phase: "static_asset_mount_placeholder",
          },
        },
      }),
    ]),
    [],
  );
  assert.deepEqual(
    listPluginAssetSlots([
      runtimePlugin({
        package: {
          frontend_assets: {
            plugin_id: "advanced_file_viewers",
            asset_schema: "unknown.schema",
            slots: ["file_viewer"],
            assets: ["viewer.js"],
            phase: "static_asset_mount_placeholder",
          },
        },
      }),
    ]),
    [],
  );
});

test("plugin asset URLs are limited to declared safe relative assets", () => {
  const entry = listPluginAssetSlots([runtimePlugin()])[0];

  assert.equal(buildPluginAssetUrl(entry, "viewer.js"), "/plugin-assets/advanced_file_viewers/viewer.js");
  assert.equal(buildPluginAssetUrl(entry, "missing.js"), null);
  assert.equal(buildPluginAssetUrl(entry, "../plugin.yaml"), null);
  assert.equal(buildPluginAssetUrl(entry, "https://example.test/viewer.js"), null);
});

test("plugin asset slot registry rejects unsafe declared asset paths", () => {
  assert.deepEqual(
    listPluginAssetSlots([
      runtimePlugin({
        package: {
          frontend_assets: {
            plugin_id: "advanced_file_viewers",
            asset_schema: PLUGIN_FRONTEND_ASSET_SCHEMA,
            slots: ["file_viewer"],
            assets: ["../escape.js"],
            phase: "static_asset_mount_placeholder",
          },
        },
      }),
    ]),
    [],
  );
});
