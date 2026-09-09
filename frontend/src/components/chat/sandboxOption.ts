/**
 * 会话沙箱选择器的动态适配（纯函数，独立于 React 便于测试）。
 *
 * 显示矩阵（2026-09-06 修订）：
 * - 云端档始终显示；
 * - 本地档始终显示：离线（无论纯 web 还是壳内）置灰但可选择，面板内
 *   附下载引导（ChatInputSelectors 的 footer 入口）；此前纯 web 离线
 *   整档隐藏导致用户不知道本地沙箱存在；
 * - 会话恢复到 local 但当前无 daemon：原样显示 local（置灰），不改已存值。
 */
import type { TFunction } from "i18next";
import type { AgentOption } from "../../types";

export const SANDBOX_AGENT_OPTION_KEY = "sandbox";

export const SANDBOX_LOCAL_VALUE = "local";

export interface SandboxOptionVisibility {
  /** 是否在桌面壳（Tauri）内。 */
  shell: boolean;
  /** daemon 是否在线（GET /api/sandbox/status）。 */
  online: boolean;
}

/**
 * 按可见性裁剪 sandbox 选项的档位列表，并给出显示值。
 * 注意返回的 value 仅用于展示；已存会话值不被改写。
 */
export function adaptSandboxAgentOption(
  option: AgentOption,
  visibility: SandboxOptionVisibility,
  value: boolean | string | number,
): { option: AgentOption; value: boolean | string | number } {
  const options: AgentOption["options"] = [];
  for (const entry of option.options ?? []) {
    if (entry.value === SANDBOX_LOCAL_VALUE && !visibility.online) {
      options.push({ ...entry, disabled: true }); // 离线：置灰但可选择
      continue;
    }
    options.push(entry);
  }

  return { option: { ...option, options }, value };
}

/**
 * 沙箱选择器在 RunModePopover 入口条目上的呈现信息：
 * has = 会话是否存在沙箱选项；label = 当前档位（云端/本地）的已翻译名。
 * label 取已存值（未存时回落 default），与面板内选中态同源。
 */
export function resolveSandboxPresentation(
  agentOptions: Record<string, AgentOption> | undefined,
  agentOptionValues: Record<string, boolean | string | number>,
  t: TFunction,
): { has: boolean; label?: string } {
  const option = agentOptions?.[SANDBOX_AGENT_OPTION_KEY];
  if (!option) return { has: false };
  const value = agentOptionValues[SANDBOX_AGENT_OPTION_KEY] ?? option.default;
  const selected = option.options?.find((item) => item.value === value);
  return {
    has: true,
    label: selected?.label_key
      ? t(selected.label_key)
      : selected?.label || String(value),
  };
}

// ---------------------------------------------------------------------------
// 会话级机器选择（多机 daemon）：sandbox_machine_id 会话级选机
// ---------------------------------------------------------------------------

import type { SandboxMachine } from "../../services/api/sandbox";

/** 会话选机键：与后端 agent_options.sandbox_machine_id 契约一致。 */
export const SANDBOX_MACHINE_AGENT_OPTION_KEY = "sandbox_machine_id";

// ---------------------------------------------------------------------------
// 统一沙箱面板（档位 + 执行设备同弹窗）
// ---------------------------------------------------------------------------

/** 统一面板的设备行描述：value "" = 自动（后端默认解析：默认机→唯一在线→legacy）。 */
export interface SandboxMachineRow {
  value: string;
  label: string;
  /** 行对应机器的 machine_id（自动档无）。 */
  machineId?: string;
  platform?: string;
  online: boolean;
  /** 当前设备：壳内读 ~/.lambchat/sandbox.json 的 machine_id 比对命中。 */
  isCurrent: boolean;
  disabled?: boolean;
}

/** 机器在线判定：缺省（旧后端无该字段）按在线处理，兼容迁移窗口。 */
export function isMachineOnline(machine: SandboxMachine): boolean {
  return machine.online !== false;
}

/**
 * 由机器列表构建统一面板的设备行：自动 → 默认机 → 其余在线 → 离线，
 * 离线置灰标注；当前设备即使离线也标注——用户需要认出"哪台是我这台"，
 * 与可否选为执行目标无关。
 */
export function buildSandboxMachineRows(
  machines: SandboxMachine[],
  defaultMachineId: string | null,
  currentMachineId: string | null,
  t: (key: string) => string,
): SandboxMachineRow[] {
  if (machines.length === 0) return [];
  const onlineMachines = machines.filter(isMachineOnline);
  const ordered = [
    ...onlineMachines.filter((m) => m.machine_id === defaultMachineId),
    ...onlineMachines.filter((m) => m.machine_id !== defaultMachineId),
    ...machines.filter((m) => !isMachineOnline(m)),
  ];
  return [
    {
      value: "",
      label: t("agentOptions.sandboxMachine.auto"),
      online: true,
      isCurrent: false,
    },
    ...ordered.map((m) => ({
      value: m.machine_id,
      label: isMachineOnline(m)
        ? m.name || m.machine_id
        : `${m.name || m.machine_id} · ${t("agentOptions.sandboxMachine.offline")}`,
      machineId: m.machine_id,
      platform: m.platform,
      online: isMachineOnline(m),
      isCurrent: !!currentMachineId && m.machine_id === currentMachineId,
      disabled: !isMachineOnline(m) || undefined,
    })),
  ];
}

/**
 * 沙箱入口按钮（工具栏 chip / RunModePopover 徽标）的展示标签：
 * 云端档或本地自动 → 档位名；本地指定机 → 「档位名 · 机器名」。
 * 机器值不在列表（他端删除/失效）回落档位名，不展示幽灵机器。
 */
export function resolveSandboxButtonLabel(opts: {
  sandboxValue: boolean | string | number;
  tierLabel: string;
  machineValue: string | null | undefined;
  machines: SandboxMachine[];
}): string {
  if (opts.sandboxValue !== SANDBOX_LOCAL_VALUE) return opts.tierLabel;
  const machineId =
    typeof opts.machineValue === "string" ? opts.machineValue : "";
  if (!machineId) return opts.tierLabel;
  const machine = opts.machines.find((m) => m.machine_id === machineId);
  if (!machine) return opts.tierLabel;
  return `${opts.tierLabel} · ${machine.name || machine.machine_id}`;
}
