import assert from "node:assert/strict";
import test from "node:test";

import {
  buildScheduledTaskInputPayload,
  getScheduledTaskPersonaPresetId,
  getScheduledTaskPluginOptionStringValue,
} from "../scheduledTaskPayload.ts";

test("clearing the model removes stale scheduled task agent options", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        agent_options: {
          model_id: "old-model-id",
          model: "old-model",
          _resolved_model_config: { id: "old-model-id" },
        },
      },
      {
        agentId: "fast",
        modelId: "",
        modelValue: "",
        availableModels: null,
      },
    ),
    {
      message: "run",
    },
  );
});

test("clearing the model preserves non-model agent options", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        agent_options: {
          model_id: "old-model-id",
          temperature: 0.2,
        },
      },
      {
        agentId: "fast",
        modelId: "",
        modelValue: "",
        availableModels: null,
      },
    ),
    {
      message: "run",
      agent_options: {
        temperature: 0.2,
      },
    },
  );
});

test("scheduled tasks without plugin declarations preserve existing plugin options", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        team_id: "team-old",
        plugin_options: {
          agent_team: { SELECTED_TEAM_ID: "team-old" },
          another_plugin: { KEEP: true },
        },
      },
      {
        agentId: "fast",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-1",
      },
    ),
    {
      message: "run",
      persona_preset_id: "persona-1",
      plugin_options: {
        agent_team: { SELECTED_TEAM_ID: "team-old" },
        another_plugin: { KEEP: true },
      },
    },
  );
});

test("scheduled tasks store declared plugin option values generically", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        persona_preset_id: "persona-old",
        plugin_options: {
          another_plugin: { KEEP: true },
        },
      },
      {
        agentId: "team",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-1",
        pluginOptionValues: {
          agent_team: { SELECTED_TEAM_ID: "team-1" },
        },
        pluginOptionDeclarations: [
          {
            plugin_id: "agent_team",
            key: "SELECTED_TEAM_ID",
            suppresses_core_persona_selector: true,
          },
        ],
      },
    ),
    {
      message: "run",
      plugin_options: {
        agent_team: { SELECTED_TEAM_ID: "team-1" },
        another_plugin: { KEEP: true },
      },
    },
  );
});

test("scheduled task payload can merge declared plugin option values generically", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        plugin_options: {
          agent_team: { SELECTED_TEAM_ID: "team-old" },
          retention_plugin: { WINDOW_DAYS: 7 },
        },
      },
      {
        agentId: "reporter",
        modelId: "",
        modelValue: "",
        availableModels: null,
        pluginOptionValues: {
          retention_plugin: { WINDOW_DAYS: 30 },
          export_plugin: { FORMAT: "csv" },
        },
      },
    ),
    {
      message: "run",
      plugin_options: {
        retention_plugin: { WINDOW_DAYS: 30 },
        export_plugin: { FORMAT: "csv" },
      },
    },
  );
});

test("scheduled task payload retains only declared plugin options when declarations are supplied", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        plugin_options: {
          agent_team: { SELECTED_TEAM_ID: "team-old" },
          retention_plugin: { WINDOW_DAYS: 7, STALE: true },
        },
      },
      {
        agentId: "reporter",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-1",
        pluginOptionValues: {
          retention_plugin: { WINDOW_DAYS: 30, STALE: true },
          export_plugin: { FORMAT: "csv" },
        },
        pluginOptionDeclarations: [
          { plugin_id: "retention_plugin", key: "WINDOW_DAYS" },
          { plugin_id: "export_plugin", key: "FORMAT" },
        ],
      },
    ),
    {
      message: "run",
      persona_preset_id: "persona-1",
      plugin_options: {
        retention_plugin: { WINDOW_DAYS: 30 },
        export_plugin: { FORMAT: "csv" },
      },
    },
  );
});

test("empty plugin option declarations do not suppress core persona payload", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
      },
      {
        agentId: "fast",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-1",
        pluginOptionDeclarations: [],
      },
    ),
    {
      message: "run",
      persona_preset_id: "persona-1",
    },
  );
});

test("plugin option declarations suppress core persona only when requested", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
      },
      {
        agentId: "team",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-ignored",
        pluginOptionValues: {
          agent_team: { SELECTED_TEAM_ID: "team-1" },
        },
        pluginOptionDeclarations: [
          {
            plugin_id: "agent_team",
            key: "SELECTED_TEAM_ID",
            suppresses_core_persona_selector: true,
          },
        ],
      },
    ),
    {
      message: "run",
      plugin_options: {
        agent_team: { SELECTED_TEAM_ID: "team-1" },
      },
    },
  );
});

test("scheduled task payload imports legacy fields through plugin declarations", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        team_id: "legacy-team",
      },
      {
        agentId: "team",
        modelId: "",
        modelValue: "",
        availableModels: null,
        pluginOptionDeclarations: [
          {
            plugin_id: "agent_team",
            key: "SELECTED_TEAM_ID",
            legacy_payload_keys: ["team_id"],
          },
        ],
      },
    ),
    {
      message: "run",
      plugin_options: {
        agent_team: { SELECTED_TEAM_ID: "legacy-team" },
      },
    },
  );
});

test("scheduled tasks preserve explicit plugin option values", () => {
  assert.deepEqual(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        team_id: "legacy-team",
      },
      {
        agentId: "team",
        modelId: "",
        modelValue: "",
        availableModels: null,
        pluginOptionValues: {
          agent_team: { SELECTED_TEAM_ID: "team-from-plugin-option" },
        },
        pluginOptionDeclarations: [
          {
            plugin_id: "agent_team",
            key: "SELECTED_TEAM_ID",
            legacy_payload_keys: ["team_id"],
          },
        ],
      },
    ),
    {
      message: "run",
      plugin_options: {
        agent_team: { SELECTED_TEAM_ID: "team-from-plugin-option" },
      },
    },
  );
});

test("scheduled task payload id readers use plugin declarations", () => {
  assert.equal(
    getScheduledTaskPersonaPresetId({ persona_preset_id: "persona-1" }),
    "persona-1",
  );
  assert.equal(getScheduledTaskPersonaPresetId({ persona_preset_id: 1 }), "");
  assert.equal(
    getScheduledTaskPluginOptionStringValue(
      {
        team_id: "legacy-team",
        plugin_options: { agent_team: { SELECTED_TEAM_ID: "team-1" } },
      },
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        legacy_payload_keys: ["team_id"],
      },
    ),
    "team-1",
  );
  assert.equal(
    getScheduledTaskPluginOptionStringValue(
      { team_id: "legacy-team" },
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        legacy_payload_keys: ["team_id"],
      },
    ),
    "legacy-team",
  );
  assert.equal(
    getScheduledTaskPluginOptionStringValue(
      { team_id: null },
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        legacy_payload_keys: ["team_id"],
      },
    ),
    "",
  );
});
