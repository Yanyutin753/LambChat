/** 会话级机器选择器（纯函数）：统一面板设备行构造与入口标签 */
import { describe, expect, it } from "vitest";
import type { SandboxMachine } from "../../../services/api/sandbox";
import { buildSandboxMachineRows, resolveSandboxButtonLabel } from "../sandboxOption";

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

// ---------------------------------------------------------------------------
// 统一沙箱面板（档位 + 执行设备同弹窗）：设备行构造与按钮标签
// ---------------------------------------------------------------------------

function machine(
  id: string,
  opts: Partial<Parameters<typeof buildSandboxMachineRows>[0][number]> = {},
) {
  return {
    machine_id: id,
    name: id.toUpperCase(),
    platform: "linux",
    version: "0.4.0",
    confirm_policy: "all",
    online: true,
    last_seen: 1700_000_000,
    ...opts,
  };
}

describe("buildSandboxMachineRows", () => {
  it("自动档居首，默认机置顶，当前设备带标识", () => {
    const rows = buildSandboxMachineRows(
      [machine("srv1"), machine("mac1"), machine("off1", { online: false })],
      "srv1",
      "mac1",
      t,
    );
    expect(rows[0]).toMatchObject({
      value: "",
      label: t("agentOptions.sandboxMachine.auto"),
      online: true,
      isCurrent: false,
    });
    // 排序与 buildSandboxMachineOption 同规则：自动 → 默认机 → 其余在线 → 离线
    expect(rows.map((r) => r.value)).toEqual(["", "srv1", "mac1", "off1"]);
    expect(rows.find((r) => r.value === "mac1")?.isCurrent).toBe(true);
    expect(rows.find((r) => r.value === "srv1")?.isCurrent).toBe(false);
  });

  it("离线机置灰并标注离线；当前设备为离线机时仍标注", () => {
    const rows = buildSandboxMachineRows(
      [machine("off1", { online: false })],
      null,
      "off1",
      t,
    );
    const off = rows.find((r) => r.value === "off1")!;
    expect(off.disabled).toBe(true);
    expect(off.label).toContain("agentOptions.sandboxMachine.offline");
    expect(off.isCurrent).toBe(true);
  });

  it("currentMachineId 为 null（纯 web 端）时无当前标识", () => {
    const rows = buildSandboxMachineRows([machine("on1")], null, null, t);
    expect(rows.every((r) => !r.isCurrent)).toBe(true);
  });

  it("行携带平台与在线信息供 UI 渲染图标", () => {
    const rows = buildSandboxMachineRows(
      [machine("win1", { platform: "win32" })],
      null,
      null,
      t,
    );
    const row = rows.find((r) => r.value === "win1")!;
    expect(row.platform).toBe("win32");
    expect(row.online).toBe(true);
  });
});

describe("resolveSandboxButtonLabel", () => {
  const tierLabel = "本地";

  it("云端档显示档位名", () => {
    expect(
      resolveSandboxButtonLabel({
        sandboxValue: "cloud",
        tierLabel: "云端",
        machineValue: "mac1",
        machines,
      }),
    ).toBe("云端");
  });

  it("本地 + 自动（无指定机）显示档位名", () => {
    expect(
      resolveSandboxButtonLabel({
        sandboxValue: "local",
        tierLabel,
        machineValue: undefined,
        machines,
      }),
    ).toBe(tierLabel);
    expect(
      resolveSandboxButtonLabel({
        sandboxValue: "local",
        tierLabel,
        machineValue: "",
        machines,
      }),
    ).toBe(tierLabel);
  });

  it("本地 + 指定机器显示「档位名 · 机器名」", () => {
    expect(
      resolveSandboxButtonLabel({
        sandboxValue: "local",
        tierLabel,
        machineValue: "mac1",
        machines,
      }),
    ).toBe("本地 · MacBook");
    // 无名机器回落 machine_id
    expect(
      resolveSandboxButtonLabel({
        sandboxValue: "local",
        tierLabel,
        machineValue: "srv1",
        machines: [machine("srv1", { name: "" })],
      }),
    ).toBe("本地 · srv1");
  });

  it("本地 + 机器值已失效（不在列表）回落档位名", () => {
    expect(
      resolveSandboxButtonLabel({
        sandboxValue: "local",
        tierLabel,
        machineValue: "gone1",
        machines,
      }),
    ).toBe(tierLabel);
  });
});
