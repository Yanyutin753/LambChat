import {
  buildCheckpointForkUrl,
  buildMessageCheckpointUrl,
  buildMessageForkUrl,
  buildSessionRunsUrl,
  buildSessionEventsUrl,
  buildSubmitChatBody,
} from "../session.ts";

test("builds a session list url with favorites_only", () => {
  const searchParams = new URLSearchParams();
  searchParams.set("favorites_only", "true");
  expect(`/api/sessions?${searchParams.toString()}`).toBe(
    "/api/sessions?favorites_only=true",
  );
});

test("builds the default session runs url", () => {
  expect(buildSessionRunsUrl("session-1")).toBe("/api/sessions/session-1/runs");
});

test("includes trace_id when looking up a specific run by trace", () => {
  expect(buildSessionRunsUrl("session-1", { trace_id: "trace-123" })).toBe(
    "/api/sessions/session-1/runs?trace_id=trace-123",
  );
});

test("builds compact chat history event urls only when requested", () => {
  expect(
    buildSessionEventsUrl("session-1", {
      include_active_user_message: true,
      compact_message_chunks: true,
    }),
  ).toBe(
    "/api/sessions/session-1/events?include_active_user_message=true&compact_message_chunks=true",
  );
  expect(buildSessionEventsUrl("session-1")).toBe(
    "/api/sessions/session-1/events",
  );
});

test("includes user_timezone in the submit chat body when available", () => {
  expect(
    buildSubmitChatBody({
      message: "hello",
      sessionId: "session-1",
      userTimezone: "Asia/Shanghai",
    }),
  ).toEqual({
    message: "hello",
    session_id: "session-1",
    agent_options: undefined,
    attachments: undefined,
    disabled_skills: undefined,
    enabled_skills: undefined,
    persona_preset_id: undefined,
    disabled_mcp_tools: undefined,
    user_timezone: "Asia/Shanghai",
  });
});

test("includes persona preset fields in the submit chat body", () => {
  expect(
    buildSubmitChatBody({
      message: "hello",
      personaPresetId: "preset-1",
      enabledSkills: ["planning"],
    }),
  ).toEqual({
    message: "hello",
    session_id: undefined,
    agent_options: undefined,
    attachments: undefined,
    disabled_skills: undefined,
    enabled_skills: ["planning"],
    persona_preset_id: "preset-1",
    disabled_mcp_tools: undefined,
  });
});

test("includes team_id in the submit chat body when a team is selected", () => {
  expect(
    buildSubmitChatBody({
      message: "hello",
      teamId: "team-1",
    }),
  ).toEqual({
    message: "hello",
    session_id: undefined,
    agent_options: undefined,
    attachments: undefined,
    disabled_skills: undefined,
    enabled_skills: undefined,
    persona_preset_id: undefined,
    disabled_mcp_tools: undefined,
    team_id: "team-1",
  });
});

test("includes a run-scoped goal in the submit chat body", () => {
  expect(
    buildSubmitChatBody({
      message: "continue",
      goal: {
        objective: "finish docs",
        rubric: "- docs updated",
        max_iterations: 3,
      },
    }),
  ).toEqual({
    message: "continue",
    session_id: undefined,
    agent_options: undefined,
    attachments: undefined,
    disabled_skills: undefined,
    enabled_skills: undefined,
    persona_preset_id: undefined,
    disabled_mcp_tools: undefined,
    goal: {
      objective: "finish docs",
      rubric: "- docs updated",
      max_iterations: 3,
    },
  });
});

test("builds the message fork url", () => {
  expect(buildMessageForkUrl("session-1", "message-1")).toBe(
    "/api/sessions/session-1/messages/message-1/fork",
  );
});

test("builds the message checkpoint url", () => {
  expect(buildMessageCheckpointUrl("session-1", "message-1")).toBe(
    "/api/sessions/session-1/messages/message-1/checkpoints",
  );
});

test("builds the checkpoint fork url", () => {
  expect(buildCheckpointForkUrl("session-1", "checkpoint-1")).toBe(
    "/api/sessions/session-1/checkpoints/checkpoint-1/fork",
  );
});

test("strips client-only long text fields from submit attachments", () => {
  expect(
    buildSubmitChatBody({
      message: "hello",
      attachments: [
        {
          id: "att-1",
          key: "k1",
          name: "long.txt",
          type: "document",
          mimeType: "text/plain",
          size: 4,
          url: "/api/upload/file/k1",
          fromLongText: true,
          localOriginalText: "secret",
          isUploading: false,
          uploadProgress: 100,
        },
      ],
    }),
  ).toEqual({
    message: "hello",
    session_id: undefined,
    agent_options: undefined,
    attachments: [
      {
        id: "att-1",
        key: "k1",
        name: "long.txt",
        type: "document",
        mimeType: "text/plain",
        size: 4,
        url: "/api/upload/file/k1",
      },
    ],
    disabled_skills: undefined,
    enabled_skills: undefined,
    persona_preset_id: undefined,
    disabled_mcp_tools: undefined,
  });
});
