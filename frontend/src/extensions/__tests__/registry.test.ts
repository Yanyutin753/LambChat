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

  expect(registry.list({ type: "skill" }).map((item) => item.id)).toEqual([
    "skills",
  ]);
  expect(registry.list({ enabled: false }).map((item) => item.id)).toEqual([
    "feedback",
  ]);
  expect(registry.get("skills")?.tags).toEqual(["core"]);
  expect(registry.permissions()).toEqual(["skill:read", "skill:write"]);
  expect(registry.permissions({ enabledOnly: false })).toEqual([
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

  expect(registry.get("pdf-viewer")?.type).toBe("file_viewer");
  expect(registry.get("agent-team")?.type).toBe("agent_team");
  expect(registry.get("user-agent")?.type).toBe("user_agent");
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

  expect(registry.list({ enabled: true }).map((plugin) => plugin.id)).toEqual([
    "feedback",
  ]);
  expect(registry.routes().map((route) => route.id)).toEqual(["feedback-route"]);
  expect(registry.panels().map((panel) => panel.id)).toEqual(["feedback-panel"]);
  expect(registry.navItems().map((item) => item.id)).toEqual(["feedback-nav"]);
  expect(registry.routes({ enabled: false }).map((route) => route.id)).toEqual([
    "audio-route",
  ]);
  expect(registry.panels({ enabled: false }).map((panel) => panel.id)).toEqual([
    "audio-panel",
  ]);
  expect(registry.navItems({ enabled: false }).map((item) => item.id)).toEqual([
    "audio-nav",
  ]);
  expect(registry.settingsSections()).toEqual(["feedback:settings"]);
  expect(registry.toolRenderers()).toEqual(["feedback.summary"]);
  expect(registry.i18nNamespaces()).toEqual(["feedback"]);
  expect(registry.settingsSections({ enabled: false })).toEqual(["audio:settings"]);
  expect(registry.toolRenderers({ enabled: false })).toEqual(["audio.transcribe"]);
  expect(registry.i18nNamespaces({ enabled: false })).toEqual(["audio"]);
  expect(registry.permissions()).toEqual([
    "feedback:read",
    "feedback:write",
    "feedback:admin",
  ]);
  expect(registry.permissions({ enabledOnly: false })).toEqual([
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

  expect(registry.routes().map((route) => route.id)).toEqual([]);
  expect(registry.panels().map((panel) => panel.id)).toEqual([]);
  expect(registry.navItems().map((item) => item.id)).toEqual([]);
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

  expect(registry.navItems().map((item) => item.id)).toEqual(["first", "later"]);
  expect(registry.get("plugin-a")?.navItems?.map((item) => item.id)).toEqual([
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

  expect(extension?.type).toBe("plugin");
  expect(extension?.publisher).toBe("LambChat");
  expect(extension?.enabled).toBe(false);
  expect(extension?.permissions).toEqual(["team:read", "team:write"]);
  expect(extension?.compatibility?.apiVersion).toBe("v1");
});

test("collectPluginPermissions dedupes top-level and contribution permissions", () => {
  expect(collectPluginPermissions({
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
    })).toEqual(["feedback:read", "feedback:write"]);
});
