/**
 * 会话沙箱选择器的动态适配（纯函数，独立于 React 便于测试）。
 *
 * 显示矩阵（2026-09-05 确认）：
 * - 云端档始终显示；
 * - 本地档：桌面壳内始终显示（离线置灰但可选择）；纯 web 仅当
 *   useSandboxStatus 报 online 时渲染（用户可能在本机手动跑 CLI daemon）；
 * - 会话恢复到 local 但当前无 daemon：回退显示云端档，不静默改已存值。
 */
import type { AgentOption } from "../../types";

export const SANDBOX_AGENT_OPTION_KEY = "sandbox";

/** 本地档兜底显示值：本地档不可见时的回退档位。 */
export const SANDBOX_CLOUD_VALUE = "cloud";
export const SANDBOX_LOCAL_VALUE = "local";

export interface SandboxOptionVisibility {
  /** 是否在桌面壳（Tauri）内。 */
  shell: boolean;
  /** daemon 是否在线（GET /api/sandbox/status）。 */
  online: boolean;
}

export function isSandboxLocalVisible(visibility: SandboxOptionVisibility): boolean {
  return visibility.shell || visibility.online;
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
  const localVisible = isSandboxLocalVisible(visibility);
  const options: AgentOption["options"] = [];
  for (const entry of option.options ?? []) {
    if (entry.value === SANDBOX_LOCAL_VALUE && !localVisible) {
      continue; // 纯 web 且离线：本地档整个不出现
    }
    if (entry.value === SANDBOX_LOCAL_VALUE && !visibility.online) {
      options.push({ ...entry, disabled: true }); // 壳内离线：置灰但可选择
      continue;
    }
    options.push(entry);
  }

  const displayValue =
    value === SANDBOX_LOCAL_VALUE && !localVisible
      ? SANDBOX_CLOUD_VALUE
      : value;

  return { option: { ...option, options }, value: displayValue };
}
