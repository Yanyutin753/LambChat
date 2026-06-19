import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

interface FrontendPluginManifest {
  plugin_id?: string;
  frontend?: {
    app_panels?: Array<{ renderer?: string }>;
    message_actions?: Array<{ renderer?: string }>;
    chat_input_options?: Array<{ selected_renderer?: string }>;
    chat_input_panels?: Array<{ renderer?: string }>;
    mention_providers?: Array<{ provider?: string }>;
    welcome_surfaces?: Array<{ renderer?: string }>;
    assistant_identity_resolvers?: Array<{ resolver?: string }>;
    project_options?: Array<{ renderer?: string }>;
    session_options?: Array<{ renderer?: string }>;
    channel_options?: Array<{ renderer?: string }>;
    channel_connectors?: Array<{ panel_renderer?: string }>;
    scheduled_task_options?: Array<{ renderer?: string }>;
  };
}

interface RegistryReference {
  manifest: string;
  area: string;
  value: string;
  registrySource: string;
}

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = fileURLToPath(new URL("../../../../", import.meta.url));

const registrySources = {
  appPanel: source("frontend/src/components/layout/AppContent/TabContent.tsx"),
  messageAction: source(
    "frontend/src/components/chat/ChatMessage/messageActionRenderers.tsx",
  ),
  chatInputPanel: source("frontend/src/components/chat/chatInputPanelRenderers.tsx"),
  chatInputSelected: source(
    "frontend/src/components/chat/chatInputSelectedRenderers.tsx",
  ),
  mentionProvider: source(
    "frontend/src/components/chat/chatMentionProviderRenderers.tsx",
  ),
  welcomeSurface: source("frontend/src/components/chat/welcomeSurfaceRenderers.tsx"),
  assistantIdentity: source(
    "frontend/src/components/chat/chatAssistantIdentityResolvers.ts",
  ),
  projectOption: source("frontend/src/components/sidebar/projectOptionRenderers.tsx"),
  channelOption: source(
    "frontend/src/components/panels/channel/ChannelPluginOptions.tsx",
  ),
  channelConnectorPanel: source(
    "frontend/src/components/pages/channelConnectorPanelRenderers.tsx",
  ),
  scheduledTaskOption: source(
    "frontend/src/components/panels/ScheduledTaskPanel/scheduledTaskOptionRenderers.tsx",
  ),
};

function source(pathFromRoot: string): string {
  return readFileSync(join(repoRoot, pathFromRoot), "utf8");
}

function listFrontendManifestPaths(): string[] {
  const pluginRoot = join(repoRoot, "plugins");
  const results: string[] = [];

  function visit(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        visit(path);
        continue;
      }
      if (entry.name !== "plugin.json") continue;
      if (path.replace(/\\/g, "/").endsWith("/frontend/plugin.json")) {
        results.push(path);
      }
    }
  }

  visit(pluginRoot);
  return results.sort();
}

function readManifest(path: string): FrontendPluginManifest {
  return JSON.parse(readFileSync(path, "utf8")) as FrontendPluginManifest;
}

function referencesForManifest(path: string): RegistryReference[] {
  const manifest = readManifest(path);
  const frontend = manifest.frontend ?? {};
  const manifestName = relative(repoRoot, path).replace(/\\/g, "/");
  const references: RegistryReference[] = [];

  function add(area: string, value: string | undefined, registrySource: string) {
    if (!value) return;
    references.push({ manifest: manifestName, area, value, registrySource });
  }

  for (const item of frontend.app_panels ?? []) {
    add("app_panels.renderer", item.renderer, registrySources.appPanel);
  }
  for (const item of frontend.message_actions ?? []) {
    add("message_actions.renderer", item.renderer, registrySources.messageAction);
  }
  for (const item of frontend.chat_input_options ?? []) {
    add(
      "chat_input_options.selected_renderer",
      item.selected_renderer,
      registrySources.chatInputSelected,
    );
  }
  for (const item of frontend.chat_input_panels ?? []) {
    add("chat_input_panels.renderer", item.renderer, registrySources.chatInputPanel);
  }
  for (const item of frontend.mention_providers ?? []) {
    add("mention_providers.provider", item.provider, registrySources.mentionProvider);
  }
  for (const item of frontend.welcome_surfaces ?? []) {
    add("welcome_surfaces.renderer", item.renderer, registrySources.welcomeSurface);
  }
  for (const item of frontend.assistant_identity_resolvers ?? []) {
    add(
      "assistant_identity_resolvers.resolver",
      item.resolver,
      registrySources.assistantIdentity,
    );
  }
  for (const item of frontend.project_options ?? []) {
    add("project_options.renderer", item.renderer, registrySources.projectOption);
  }
  for (const item of frontend.session_options ?? []) {
    add("session_options.renderer", item.renderer, registrySources.projectOption);
  }
  for (const item of frontend.channel_options ?? []) {
    add("channel_options.renderer", item.renderer, registrySources.channelOption);
  }
  for (const item of frontend.channel_connectors ?? []) {
    add(
      "channel_connectors.panel_renderer",
      item.panel_renderer,
      registrySources.channelConnectorPanel,
    );
  }
  for (const item of frontend.scheduled_task_options ?? []) {
    add(
      "scheduled_task_options.renderer",
      item.renderer,
      registrySources.scheduledTaskOption,
    );
  }

  return references;
}

function escapedStringLiteral(value: string): RegExp {
  return new RegExp(JSON.stringify(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

test("all plugin-declared frontend renderers are registered in controlled host registries", () => {
  assert.ok(existsSync(join(repoRoot, "plugins")), "plugins directory exists");
  const references = listFrontendManifestPaths().flatMap(referencesForManifest);
  assert.ok(references.length > 0, "frontend plugin manifests declare registry-backed references");

  const missing = references.filter(
    (reference) => !escapedStringLiteral(reference.value).test(reference.registrySource),
  );

  assert.deepEqual(
    missing.map((reference) => ({
      manifest: reference.manifest,
      area: reference.area,
      value: reference.value,
    })),
    [],
    "plugin frontend declarations must map to static host registries before runtime can render them",
  );
});

test("plugin renderer registry coverage test is rooted in the repository, not the test folder", () => {
  assert.equal(relative(repoRoot, testDir).replace(/\\/g, "/"), "frontend/src/extensions/__tests__");
});
