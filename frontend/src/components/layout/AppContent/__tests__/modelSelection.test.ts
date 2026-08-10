import { resolveModelSelection } from "../modelSelection";

const models = [
  { id: "session-id", value: "provider/session" },
  { id: "user-id", value: "provider/user" },
  { id: "system-id", value: "provider/system" },
];

test("prefers the saved session model over user and system defaults", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      sessionModelId: "session-id",
      sessionModelValue: "provider/session",
      userDefaultId: "user-id",
      userDefaultValue: "provider/user",
      systemDefaultId: "system-id",
      systemDefaultValue: "provider/system",
    }),
  ).toEqual({ modelId: "session-id", modelValue: "provider/session" });
});

test("prefers the user default when no session model exists", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      userDefaultId: "user-id",
      userDefaultValue: "provider/user",
      systemDefaultId: "system-id",
      systemDefaultValue: "provider/system",
    }),
  ).toEqual({ modelId: "user-id", modelValue: "provider/user" });
});

test("uses the system initial model when no session or user model exists", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      systemDefaultId: "system-id",
      systemDefaultValue: "provider/system",
    }),
  ).toEqual({ modelId: "system-id", modelValue: "provider/system" });
});

test("uses the first available model only after all configured tiers are absent", () => {
  expect(resolveModelSelection({ availableModels: models })).toEqual({
    modelId: "session-id",
    modelValue: "provider/session",
  });
});

test("falls through invalid session and user candidates to the system model", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      sessionModelId: "deleted-session",
      sessionModelValue: "provider/deleted-session",
      userDefaultId: "deleted-user",
      userDefaultValue: "provider/deleted-user",
      systemDefaultId: "system-id",
      systemDefaultValue: "provider/system",
    }),
  ).toEqual({ modelId: "system-id", modelValue: "provider/system" });
});

test("falls through an invalid session candidate to the user model", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      sessionModelId: "deleted-session",
      userDefaultId: "user-id",
      systemDefaultId: "system-id",
    }),
  ).toEqual({ modelId: "user-id", modelValue: "provider/user" });
});

test("uses a valid model ID and returns its canonical value", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      sessionModelId: "session-id",
      sessionModelValue: "provider/stale-value",
    }),
  ).toEqual({ modelId: "session-id", modelValue: "provider/session" });
});

test("resolves a legacy model value only when it has one match", () => {
  expect(
    resolveModelSelection({
      availableModels: models,
      sessionModelId: "deleted-id",
      sessionModelValue: "provider/user",
    }),
  ).toEqual({ modelId: "user-id", modelValue: "provider/user" });
});

test("does not choose an arbitrary ID for a duplicate legacy value", () => {
  expect(
    resolveModelSelection({
      availableModels: [
        { id: "duplicate-a", value: "provider/shared" },
        { id: "duplicate-b", value: "provider/shared" },
        { id: "system-id", value: "provider/system" },
      ],
      sessionModelValue: "provider/shared",
      systemDefaultId: "system-id",
    }),
  ).toEqual({ modelId: "system-id", modelValue: "provider/system" });
});

test("preserves the highest-priority raw candidate while models are unresolved", () => {
  expect(
    resolveModelSelection({
      availableModels: null,
      sessionModelId: "session-id",
      sessionModelValue: "provider/session",
      userDefaultId: "user-id",
      userDefaultValue: "provider/user",
      systemDefaultId: "system-id",
      systemDefaultValue: "provider/system",
    }),
  ).toEqual({ modelId: "session-id", modelValue: "provider/session" });
});

test("returns an empty selection when availability is known to be empty", () => {
  expect(
    resolveModelSelection({
      availableModels: [],
      sessionModelId: "session-id",
      sessionModelValue: "provider/session",
    }),
  ).toEqual({ modelId: "", modelValue: "" });
});
