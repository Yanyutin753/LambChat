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

  expect(entries).toEqual([
    {
      id: "advanced_file_viewers:file_viewer",
      pluginId: "advanced_file_viewers",
      slot: "file_viewer",
      assetSchema: PLUGIN_FRONTEND_ASSET_SCHEMA,
      assets: ["viewer.js"],
      mountPath: "/plugin-assets/advanced_file_viewers/",
    },
  ]);
  expect(hasPluginAssetSlot("file_viewer", [runtimePlugin()])).toBe(true);
  expect(findPluginAssetSlot("file_viewer", [runtimePlugin()])?.pluginId).toBe("advanced_file_viewers");
});

test("plugin asset slot registry filters disabled mismatched or unsupported bundles", () => {
  expect(listPluginAssetSlots([
      runtimePlugin({ enabled: false, executable: false, status: "disabled" }),
    ])).toEqual([]);
  expect(listPluginAssetSlots([
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
    ])).toEqual([]);
  expect(listPluginAssetSlots([
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
    ])).toEqual([]);
});

test("plugin asset URLs are limited to declared safe relative assets", () => {
  const entry = listPluginAssetSlots([runtimePlugin()])[0];

  expect(buildPluginAssetUrl(entry, "viewer.js")).toBe("/plugin-assets/advanced_file_viewers/viewer.js");
  expect(buildPluginAssetUrl(entry, "missing.js")).toBe(null);
  expect(buildPluginAssetUrl(entry, "../plugin.yaml")).toBe(null);
  expect(buildPluginAssetUrl(entry, "https://example.test/viewer.js")).toBe(null);
});

test("plugin asset slot registry rejects unsafe declared asset paths", () => {
  expect(listPluginAssetSlots([
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
    ])).toEqual([]);
});
