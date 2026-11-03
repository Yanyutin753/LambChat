import {
  buildScheduledTaskInputPayload,
  buildScheduledTaskUpdate,
  getScheduledTaskAttachments,
  getScheduledTaskPersonaPresetId,
  getScheduledTaskTeamId,
  withScheduledTaskAttachments,
} from "../scheduledTaskPayload.ts";

test("clearing the model removes stale scheduled task agent options", () => {
  expect(
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
  ).toEqual({
    message: "run",
  });
});

test("clearing the model preserves non-model agent options", () => {
  expect(
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
  ).toEqual({
    message: "run",
    agent_options: {
      temperature: 0.2,
    },
  });
});

test("non-team scheduled tasks store only persona id", () => {
  expect(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        team_id: "team-old",
      },
      {
        agentId: "fast",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-1",
        teamId: "team-1",
      },
    ),
  ).toEqual({
    message: "run",
    persona_preset_id: "persona-1",
  });
});

test("team scheduled tasks store only team id", () => {
  expect(
    buildScheduledTaskInputPayload(
      {
        message: "run",
        persona_preset_id: "persona-old",
      },
      {
        agentId: "team",
        modelId: "",
        modelValue: "",
        availableModels: null,
        personaPresetId: "persona-1",
        teamId: "team-1",
      },
    ),
  ).toEqual({
    message: "run",
    team_id: "team-1",
  });
});

test("scheduled task payload id readers ignore wrong types", () => {
  expect(
    getScheduledTaskPersonaPresetId({ persona_preset_id: "persona-1" }),
  ).toBe("persona-1");
  expect(getScheduledTaskPersonaPresetId({ persona_preset_id: 1 })).toBe("");
  expect(getScheduledTaskTeamId({ team_id: "team-1" })).toBe("team-1");
  expect(getScheduledTaskTeamId({ team_id: null })).toBe("");
});

test("scheduled task payload stores sanitized uploaded attachments", () => {
  const attachments = getScheduledTaskAttachments({
    attachments: [
      {
        id: "attachment-1",
        key: "uploads/report.pdf",
        name: "report.pdf",
        type: "document",
        mimeType: "application/pdf",
        size: 2048,
        url: "/api/upload/file/uploads/report.pdf",
        uploadProgress: 100,
        isUploading: false,
      },
      {
        id: "bad",
        name: "missing-key.txt",
        type: "document",
        mimeType: "text/plain",
        size: 42,
      },
    ],
  });

  expect(attachments).toEqual([
    {
      id: "attachment-1",
      key: "uploads/report.pdf",
      name: "report.pdf",
      type: "document",
      mimeType: "application/pdf",
      size: 2048,
      url: "/api/upload/file/uploads/report.pdf",
    },
  ]);

  expect(
    withScheduledTaskAttachments({ message: "read this" }, attachments),
  ).toEqual({
    message: "read this",
    attachments,
  });

  expect(
    withScheduledTaskAttachments({ message: "read this", attachments }, []),
  ).toEqual({
    message: "read this",
  });
});

test("task edits send only changed editable fields and never rewrite creation metadata", () => {
  const task = {
    name: "Before",
    agent_id: "search",
    trigger_type: "interval" as const,
    trigger_config: { seconds: 300 },
    input_payload: { message: "Check progress" },
    source_session_id: "original",
  };
  expect(
    buildScheduledTaskUpdate(
      task as import("../../../types/scheduledTask").ScheduledTask,
      {
        ...task,
        name: "After",
        source_session_id: "another-chat",
      },
    ),
  ).toEqual({ name: "After" });
});
