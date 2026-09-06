import { expect, test } from "vitest";
import type { AgentOption } from "../../types";
import {
  SANDBOX_AGENT_OPTION_KEY,
  adaptSandboxAgentOption,
} from "../sandboxOption";

const SANDBOX_OPTION: AgentOption = {
  type: "string",
  default: "cloud",
  label: "Sandbox",
  label_key: "agentOptions.sandbox.label",
  options: [
    { value: "cloud", label_key: "agentOptions.sandbox.options.cloud" },
    { value: "local", label_key: "agentOptions.sandbox.options.local" },
  ],
};

test("exports the sandbox agent option key", () => {
  expect(SANDBOX_AGENT_OPTION_KEY).toBe("sandbox");
});

test("pure web offline keeps the local tier visible but greyed", () => {
  const { option, value } = adaptSandboxAgentOption(
    SANDBOX_OPTION,
    {
      shell: false,
      online: false,
    },
    "local",
  );

  // 本地档始终可见（置灰 + 面板内下载引导），不再对纯 web 隐藏
  expect(option.options?.map((o) => o.value)).toEqual(["cloud", "local"]);
  expect(option.options?.find((o) => o.value === "local")?.disabled).toBe(true);
  // 已存 local 值原样显示（离线不再回退云端档）
  expect(value).toBe("local");
});

test("pure web offline with a cloud value still shows both tiers", () => {
  const { option, value } = adaptSandboxAgentOption(
    SANDBOX_OPTION,
    {
      shell: false,
      online: false,
    },
    "cloud",
  );

  expect(option.options?.map((o) => o.value)).toEqual(["cloud", "local"]);
  expect(option.options?.find((o) => o.value === "local")?.disabled).toBe(true);
  expect(value).toBe("cloud");
});

test("pure web online shows both tiers enabled", () => {
  const { option, value } = adaptSandboxAgentOption(
    SANDBOX_OPTION,
    {
      shell: false,
      online: true,
    },
    "cloud",
  );

  expect(option.options?.map((o) => o.value)).toEqual(["cloud", "local"]);
  expect(option.options?.find((o) => o.value === "local")?.disabled).toBe(
    undefined,
  );
  expect(value).toBe("cloud");
});

test("shell offline keeps the local tier visible but greyed", () => {
  const { option } = adaptSandboxAgentOption(
    SANDBOX_OPTION,
    {
      shell: true,
      online: false,
    },
    "cloud",
  );

  expect(option.options?.map((o) => o.value)).toEqual(["cloud", "local"]);
  expect(option.options?.find((o) => o.value === "local")?.disabled).toBe(true);
});

test("shell offline keeps a restored local value as the display value", () => {
  const { value } = adaptSandboxAgentOption(
    SANDBOX_OPTION,
    {
      shell: true,
      online: false,
    },
    "local",
  );

  // 壳内本地档可见：恢复值原样显示，不回退
  expect(value).toBe("local");
});

test("shell online shows both tiers fully enabled", () => {
  const { option, value } = adaptSandboxAgentOption(
    SANDBOX_OPTION,
    {
      shell: true,
      online: true,
    },
    "local",
  );

  expect(option.options?.map((o) => o.value)).toEqual(["cloud", "local"]);
  expect(option.options?.every((o) => !o.disabled)).toBe(true);
  expect(value).toBe("local");
});
