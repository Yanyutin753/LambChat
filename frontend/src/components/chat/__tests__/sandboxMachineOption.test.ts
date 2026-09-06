/** 会话级机器选择器选项构建（纯函数）：档位联动、默认值与展示名 */
import { describe, expect, it } from "vitest";
import type { SandboxMachine } from "../../../services/api/sandbox";
import {
  SANDBOX_MACHINE_AGENT_OPTION_KEY,
  buildSandboxMachineOption,
  shouldShowSandboxMachineOption,
} from "../sandboxOption";

const machines: SandboxMachine[] = [
  {
    machine_id: "mac1",
    name: "MacBook",
    platform: "darwin",
    version: "0.3.0",
    confirm_policy: "all",
    online: true,
  },
  {
    machine_id: "srv1",
    name: "Server",
    platform: "linux",
    version: "0.3.0",
    confirm_policy: "none",
    online: true,
  },
];
const t = (k: string) => k;

describe("shouldShowSandboxMachineOption", () => {
  it("仅本地档且存在机器时显示", () => {
    expect(shouldShowSandboxMachineOption("local", machines)).toBe(true);
    expect(shouldShowSandboxMachineOption("cloud", machines)).toBe(false);
    expect(shouldShowSandboxMachineOption("local", [])).toBe(false);
  });
});

describe("buildSandboxMachineOption", () => {
  it("首档为「自动（默认机）」，随后按机器生成档位", () => {
    const option = buildSandboxMachineOption(machines, "MacBook", t)!;
    expect(option).not.toBeNull();
    expect(option.options?.[0]).toMatchObject({
      value: "",
      label_key: "agentOptions.sandboxMachine.auto",
    });
    expect(option.options?.map((o) => o.value)).toEqual(["", "mac1", "srv1"]);
    expect(option.default).toBe("mac1"); // 默认机优先，无默认取首台
  });

  it("无机器返回 null（选择器整体隐藏）", () => {
    expect(buildSandboxMachineOption([], null, t)).toBeNull();
  });

  it("选项键固定为 sandbox_machine_id（与后端 agent_options 契约一致）", () => {
    expect(SANDBOX_MACHINE_AGENT_OPTION_KEY).toBe("sandbox_machine_id");
  });
});
