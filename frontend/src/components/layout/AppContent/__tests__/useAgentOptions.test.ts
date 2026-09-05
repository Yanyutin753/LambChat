import {
  buildAgentOptionValues,
  getAgentOptionSyncMode,
  normalizeAgentOptionValues,
  normalizeAgentOptions,
} from "../useAgentOptions";

test("applies backend boolean option defaults to initial values", () => {
  // 代码解释器默认开启：后端 schema 的 default 流转到初始选项值（并随 agent_options 提交）；
  // M3 起统一注入的 sandbox 选项也带出默认云端档
  expect(
    buildAgentOptionValues({
      enable_code_interpreter: {
        type: "boolean",
        default: true,
        label: "Code Interpreter",
      },
    }),
  ).toEqual({ enable_code_interpreter: true, sandbox: "cloud" });
});

test("normalizes legacy thinking off values to low", () => {
  // "off" 档已下线：思考常开，历史 off 值（含旧布尔 false）统一降级到最低档
  expect(normalizeAgentOptionValues({ enable_thinking: "off" })).toEqual({
    enable_thinking: "low",
  });
  expect(normalizeAgentOptionValues({ enable_thinking: false })).toEqual({
    enable_thinking: "low",
  });
  expect(normalizeAgentOptionValues({ enable_thinking: "disabled" })).toEqual({
    enable_thinking: "low",
  });
  expect(normalizeAgentOptionValues({ enable_thinking: "none" })).toEqual({
    enable_thinking: "low",
  });
});

test("keeps legacy boolean true on medium", () => {
  expect(normalizeAgentOptionValues({ enable_thinking: true })).toEqual({
    enable_thinking: "medium",
  });
});

test("keeps thinking tiers low/medium/high/max", () => {
  for (const level of ["low", "medium", "high", "max"]) {
    expect(normalizeAgentOptionValues({ enable_thinking: level })).toEqual({
      enable_thinking: level,
    });
  }
});

test("fallback thinking option defs exclude off tier", () => {
  // agent 未带 options 时前端兜底补全的档位定义不含 off
  const options = normalizeAgentOptions({
    enable_thinking: { type: "string", default: "low", label: "Thinking" },
  });
  const tiers = options?.enable_thinking.options?.map((o) => o.value);
  expect(tiers).toEqual(["low", "medium", "high", "max"]);
});

test("normalizes legacy off default in agent option schema", () => {
  const legacy = normalizeAgentOptions({
    enable_thinking: { type: "string", default: "off", label: "Thinking" },
  });
  expect(legacy?.enable_thinking.default).toBe("low");
});

test("passes through non-thinking options untouched", () => {
  expect(
    normalizeAgentOptionValues({ model_id: "abc", enable_code_interpreter: true }),
  ).toEqual({ model_id: "abc", enable_code_interpreter: true });
});

test("resets agent options when switching to a different agent with identical option schemas", () => {
  expect(
    getAgentOptionSyncMode({
      currentAgentId: "agent-b",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"medium"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: false,
    }),
  ).toBe("reset");
});

test("applies restored session options before skip checks", () => {
  expect(
    getAgentOptionSyncMode({
      currentAgentId: "agent-a",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"medium"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: true,
    }),
  ).toBe("restore");
});

test("preserves overlapping values only when the same agent schema changes", () => {
  expect(
    getAgentOptionSyncMode({
      currentAgentId: "agent-a",
      previousAgentId: "agent-a",
      optionsJson: '{"enable_thinking":{"default":"high"}}',
      previousOptionsJson: '{"enable_thinking":{"default":"medium"}}',
      hasPendingRestoredOptions: false,
    }),
  ).toBe("preserve");
});

// ---- 会话沙箱选项注入（M3）----

const OPTION_INPUT = {
  enable_thinking: { type: "string" as const, default: "low", label: "Thinking" },
};

test("injects a cloud-default sandbox option alongside thinking", () => {
  const options = normalizeAgentOptions(OPTION_INPUT);
  expect(options?.sandbox).toMatchObject({
    type: "string",
    default: "cloud",
    label_key: "agentOptions.sandbox.label",
    description_key: "agentOptions.sandbox.description",
    icon: "Monitor",
  });
  expect(options?.sandbox?.options?.map((o) => o.value)).toEqual([
    "cloud",
    "local",
  ]);
});

test("keeps a backend-provided sandbox option untouched", () => {
  const options = normalizeAgentOptions({
    ...OPTION_INPUT,
    sandbox: { type: "string", default: "local", label: "Custom" },
  });
  expect(options?.sandbox).toEqual({
    type: "string",
    default: "local",
    label: "Custom",
  });
});

test("does not inject sandbox when the agent defines no options", () => {
  expect(normalizeAgentOptions(undefined)).toBeUndefined();
});

test("buildAgentOptionValues seeds sandbox=cloud and preserves restored local", () => {
  // 新会话：默认云端档（随 agent_options 提交）
  expect(buildAgentOptionValues(normalizeAgentOptions(OPTION_INPUT))).toMatchObject({
    enable_thinking: "low",
    sandbox: "cloud",
  });
  // 会话恢复：已存 local 原样保留，前端不静默改写
  expect(
    buildAgentOptionValues(normalizeAgentOptions(OPTION_INPUT), {
      sandbox: "local",
    }),
  ).toMatchObject({ sandbox: "local" });
});
