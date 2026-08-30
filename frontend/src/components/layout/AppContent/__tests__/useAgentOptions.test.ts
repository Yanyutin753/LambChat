import {
  buildAgentOptionValues,
  getAgentOptionSyncMode,
  normalizeAgentOptionValues,
  normalizeAgentOptions,
} from "../useAgentOptions";

test("applies backend boolean option defaults to initial values", () => {
  // 代码解释器默认开启：后端 schema 的 default 流转到初始选项值（并随 agent_options 提交）
  expect(
    buildAgentOptionValues({
      enable_code_interpreter: {
        type: "boolean",
        default: true,
        label: "Code Interpreter",
      },
    }),
  ).toEqual({ enable_code_interpreter: true });
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
