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
// 会话级机器选择（多机 daemon）：动态注入 sandbox_machine_id 选项
// ---------------------------------------------------------------------------

import type { SandboxMachine } from "../../services/api/sandbox";

/** 会话选机键：与后端 agent_options.sandbox_machine_id 契约一致。 */
export const SANDBOX_MACHINE_AGENT_OPTION_KEY = "sandbox_machine_id";

/** 机器选择器只在「本地档 + 至少一台在线机」时有意义。 */
export function shouldShowSandboxMachineOption(
  sandboxValue: boolean | string | number,
  machines: SandboxMachine[],
): boolean {
  return sandboxValue === SANDBOX_LOCAL_VALUE && machines.length > 0;
}

/**
 * 由在线机器动态构建选择器选项：首档「自动」（后端默认解析：默认机→
 * 唯一在线→legacy），其余按机器列出。default 取用户默认机（无则首台），
 * 已存会话值不受影响（与 sandbox 档位同规则：只裁剪显示，不篡改存储）。
 */
export function buildSandboxMachineOption(
  machines: SandboxMachine[],
  defaultMachineId: string | null,
  t: (key: string) => string,
): AgentOption | null {
  if (machines.length === 0) return null;
  const options = [
    { value: "", label_key: "agentOptions.sandboxMachine.auto" },
    ...machines.map((m) => ({
      value: m.machine_id,
      label: m.name || m.machine_id,
    })),
  ];
  return {
    type: "string",
    default:
      defaultMachineId &&
      machines.some((m) => m.machine_id === defaultMachineId)
        ? defaultMachineId
        : machines[0].machine_id,
    label: t("agentOptions.sandboxMachine.label"),
    label_key: "agentOptions.sandboxMachine.label",
    description: t("agentOptions.sandboxMachine.description"),
    description_key: "agentOptions.sandboxMachine.description",
    icon: "Laptop",
    options,
  };
}
