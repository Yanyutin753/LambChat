import test from "node:test";
import assert from "node:assert/strict";

import {
  collectPluginPermissions,
  ExtensionRegistry,
  PluginRegistry,
  RegistryDuplicateError,
} from "../registry.ts";

test("extension registry registers, filters, and dedupes permissions", () => {
  const registry = new ExtensionRegistry();
  registry.register({
    id: "skills",
    type: "skill",
    name: "Skills",
    version: "1.0.0",
    publisher: "core",
    permissions: ["skill:read", "skill:read", "skill:write"],
    tags: ["core", "core", ""],
  });
  registry.register({
    id: "feedback",
    type: "plugin",
    name: "Feedback",
    version: "1.0.0",
    publisher: "core",
    permissions: ["feedback:read"],
    enabled: false,
  });

  assert.deepEqual(registry.list({ type: "skill" }).map((item) => item.id), [
    "skills",
  ]);
  assert.deepEqual(registry.list({ enabled: false }).map((item) => item.id), [
    "feedback",
  ]);
  assert.deepEqual(registry.get("skills")?.tags, ["core"]);
  assert.deepEqual(registry.permissions(), ["skill:read", "skill:write"]);
  assert.deepEqual(registry.permissions({ enabledOnly: false }), [
    "skill:read",
    "skill:write",
    "feedback:read",
  ]);
});

test("extension registry accepts reserved future extension types", () => {
  const registry = new ExtensionRegistry([
    {
      id: "pdf-viewer",
      type: "file_viewer",
      name: "PDF Viewer",
      version: "1.0.0",
      publisher: "core",
    },
    {
      id: "agent-team",
      type: "agent_team",
      name: "Agent Team",
      version: "1.0.0",
      publisher: "core",
    },
    {
      id: "user-agent",
      type: "user_agent",
      name: "User Agent",
      version: "1.0.0",
      publisher: "core",
    },
  ]);

  assert.equal(registry.get("pdf-viewer")?.type, "file_viewer");
  assert.equal(registry.get("agent-team")?.type, "agent_team");
  assert.equal(registry.get("user-agent")?.type, "user_agent");
});

test("registries reject duplicate ids", () => {
  const extensions = new ExtensionRegistry([
    {
      id: "skills",
      type: "skill",
      name: "Skills",
      version: "1.0.0",
      publisher: "core",
    },
  ]);
  assert.throws(
    () =>
      extensions.register({
        id: "skills",
        type: "skill",
        name: "Skills duplicate",
        version: "1.0.0",
        publisher: "core",
      }),
    RegistryDuplicateError,
  );

  const plugins = new PluginRegistry([
    { id: "feedback", name: "Feedback", version: "1.0.0", apiVersion: "v1" },
  ]);
  assert.throws(
    () =>
      plugins.register({
        id: "feedback",
        name: "Feedback duplicate",
        version: "1.0.0",
        apiVersion: "v1",
      }),
    RegistryDuplicateError,
  );
});

test("plugin registry exposes route, panel, nav, settings, renderer, i18n, and permissions", () => {
  const registry = new PluginRegistry([
    {
      id: "feedback",
      name: "Feedback",
      version: "1.0.0",
      apiVersion: "v1",
      permissions: ["feedback:read"],
      routes: [
        {
          id: "feedback-route",
          pluginId: "feedback",
          path: "/feedback",
          requiredPermissions: ["feedback:write"],
        },
      ],
      panels: [
        {
          id: "feedback-panel",
          pluginId: "feedback",
          slot: "settings",
          requiredPermissions: ["feedback:admin"],
        },
      ],
      navItems: [
        {
          id: "feedback-nav",
          pluginId: "feedback",
          label: "Feedback",
          path: "/feedback",
          order: 20,
        },
      ],
      settingsSections: ["feedback:settings", "feedback:settings", ""],
      toolRenderers: ["feedback.summary", "feedback.summary"],
      i18nNamespaces: ["feedback", "feedback"],
    },
    {
      id: "audio",
      name: "Audio",
      version: "1.0.0",
      apiVersion: "v1",
      enabledByDefault: false,
      routes: [
        {
          id: "audio-route",
          pluginId: "audio",
          path: "/audio",
          requiredPermissions: ["audio:transcribe"],
        },
      ],
      panels: [
        {
          id: "audio-panel",
          pluginId: "audio",
          slot: "settings",
        },
      ],
      navItems: [
        {
          id: "audio-nav",
          pluginId: "audio",
          label: "Audio",
          path: "/audio",
        },
      ],
      settingsSections: ["audio:settings"],
      toolRenderers: ["audio.transcribe"],
      i18nNamespaces: ["audio"],
    },
  ]);

  assert.deepEqual(registry.list({ enabled: true }).map((plugin) => plugin.id), [
    "feedback",
  ]);
  assert.deepEqual(registry.routes().map((route) => route.id), ["feedback-route"]);
  assert.deepEqual(registry.panels().map((panel) => panel.id), ["feedback-panel"]);
  assert.deepEqual(registry.navItems().map((item) => item.id), ["feedback-nav"]);
  assert.deepEqual(registry.routes({ enabled: false }).map((route) => route.id), [
    "audio-route",
  ]);
  assert.deepEqual(registry.panels({ enabled: false }).map((panel) => panel.id), [
    "audio-panel",
  ]);
  assert.deepEqual(registry.navItems({ enabled: false }).map((item) => item.id), [
    "audio-nav",
  ]);
  assert.deepEqual(registry.settingsSections(), ["feedback:settings"]);
  assert.deepEqual(registry.toolRenderers(), ["feedback.summary"]);
  assert.deepEqual(registry.i18nNamespaces(), ["feedback"]);
  assert.deepEqual(registry.settingsSections({ enabled: false }), ["audio:settings"]);
  assert.deepEqual(registry.toolRenderers({ enabled: false }), ["audio.transcribe"]);
  assert.deepEqual(registry.i18nNamespaces({ enabled: false }), ["audio"]);
  assert.deepEqual(registry.permissions(), [
    "feedback:read",
    "feedback:write",
    "feedback:admin",
  ]);
  assert.deepEqual(registry.permissions({ enabledOnly: false }), [
    "feedback:read",
    "feedback:write",
    "feedback:admin",
    "audio:transcribe",
  ]);
});

test("plugin registry hides disabled route, panel, and nav contributions", () => {
  const registry = new PluginRegistry([
    {
      id: "feedback",
      name: "Feedback",
      version: "1.0.0",
      apiVersion: "v1",
      routes: [
        {
          id: "feedback-route",
          pluginId: "feedback",
          path: "/feedback",
          enabled: false,
        },
      ],
      panels: [
        {
          id: "feedback-panel",
          pluginId: "feedback",
          slot: "settings",
          enabled: false,
        },
      ],
      navItems: [
        {
          id: "feedback-nav",
          pluginId: "feedback",
          label: "Feedback",
          path: "/feedback",
          enabled: false,
        },
      ],
    },
  ]);

  assert.deepEqual(registry.routes().map((route) => route.id), []);
  assert.deepEqual(registry.panels().map((panel) => panel.id), []);
  assert.deepEqual(registry.navItems().map((item) => item.id), []);
});

test("plugin nav items are ordered without mutating registration state", () => {
  const registry = new PluginRegistry([
    {
      id: "plugin-a",
      name: "Plugin A",
      version: "1.0.0",
      apiVersion: "v1",
      navItems: [
        { id: "later", pluginId: "plugin-a", label: "Later", path: "/later", order: 50 },
        { id: "first", pluginId: "plugin-a", label: "First", path: "/first", order: 10 },
      ],
    },
  ]);

  assert.deepEqual(registry.navItems().map((item) => item.id), ["first", "later"]);
  assert.deepEqual(registry.get("plugin-a")?.navItems?.map((item) => item.id), [
    "later",
    "first",
  ]);
});

test("plugin registry converts plugins to extension manifests", () => {
  const registry = new PluginRegistry([
    {
      id: "agent-team",
      name: "Agent Team",
      version: "1.0.0",
      apiVersion: "v1",
      permissions: ["team:read"],
      navItems: [
        {
          id: "agent-team-nav",
          pluginId: "agent-team",
          label: "Agent Team",
          path: "/agent-team",
          requiredPermissions: ["team:write"],
        },
      ],
      enabledByDefault: false,
    },
  ]);

  const extensions = registry.asExtensionRegistry({ publisher: "LambChat" });
  const extension = extensions.get("agent-team");

  assert.equal(extension?.type, "plugin");
  assert.equal(extension?.publisher, "LambChat");
  assert.equal(extension?.enabled, false);
  assert.deepEqual(extension?.permissions, ["team:read", "team:write"]);
  assert.equal(extension?.compatibility?.apiVersion, "v1");
});

test("collectPluginPermissions dedupes top-level and contribution permissions", () => {
  assert.deepEqual(
    collectPluginPermissions({
      id: "feedback",
      name: "Feedback",
      version: "1.0.0",
      apiVersion: "v1",
      permissions: ["feedback:read", "feedback:read"],
      routes: [
        {
          id: "feedback-route",
          pluginId: "feedback",
          path: "/feedback",
          requiredPermissions: ["feedback:write", ""],
        },
      ],
    }),
    ["feedback:read", "feedback:write"],
  );
});
