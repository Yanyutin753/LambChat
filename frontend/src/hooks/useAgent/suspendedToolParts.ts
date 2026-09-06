/**
 * 确认门挂起/悬挂工具卡处理（自 messageParts.ts 拆出，守 1000 行守门）。
 *
 * - markPendingToolsAwaiting：hitl:suspended / human_resume_started 时把
 *   pending 工具卡切「等待确认」/运行态（Codex 式确认体验）；
 * - takeOverDanglingToolPart：旧后端下 interrupt 挂起遗留的悬挂同名同参卡，
 *   由恢复重放的新 start（新 run id）原位接管，避免一次执行渲染两张卡。
 */

import type { MessagePart, ToolPart } from "../../types";

/**
 * 确认门挂起/恢复：把仍在 pending（无 result）的工具卡切「等待确认」态
 * 或切回运行中——hitl:suspended 时图整体挂起（含并行兄弟工具），全部
 * pending 工具一起标记；嵌套 subagent 子树递归处理。恢复
 * （human_resume_started）后重放的工具尚未产出 result，先统一转回运行态。
 */
export function markPendingToolsAwaiting(
  parts: MessagePart[],
  awaiting: boolean,
): MessagePart[] {
  let changed = false;
  const next = parts.map((p) => {
    if (p.type === "subagent" && p.parts) {
      const updated = markPendingToolsAwaiting(p.parts, awaiting);
      if (updated !== p.parts) {
        changed = true;
        return { ...p, parts: updated };
      }
      return p;
    }
    if (
      p.type === "tool" &&
      p.isPending &&
      p.result === undefined &&
      Boolean(p.awaitingConfirmation) !== awaiting
    ) {
      changed = true;
      return { ...p, awaitingConfirmation: awaiting };
    }
    return p;
  });
  return changed ? next : parts;
}

/**
 * 定位确认门挂起遗留的悬挂执行 part：同名、参数深相等、始终无 result
 * （interrupt 那次尝试）。旧后端下恢复重放的 tool:start 带全新 run 级 id，
 * 应原位接管这张卡而非追加第二张。
 */
function findDanglingToolIndex(
  parts: MessagePart[],
  replacement: ToolPart,
): number {
  const replacementArgs = JSON.stringify(replacement.args);
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.type !== "tool" || p.argsPartial) continue;
    if (p.name !== replacement.name) continue;
    if (p.result !== undefined || p.cancelled) continue;
    if (JSON.stringify(p.args) !== replacementArgs) continue;
    return i;
  }
  return -1;
}

/**
 * 悬挂卡原位接管：replacement 完整替换（新的 startedAt 是重放后的真实
 * 执行时刻，计时诚实）；depth 递归与 upgradeGeneratingToolPart 同构。
 * 返回 null = 无悬挂目标（走普通追加）。
 */
export function takeOverDanglingToolPart(
  parts: MessagePart[],
  replacement: ToolPart,
  targetDepth = 0,
): MessagePart[] | null {
  if (targetDepth > 0) {
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (p.type !== "subagent" || !p.parts) continue;
      const updated = takeOverDanglingToolPart(
        p.parts,
        replacement,
        targetDepth - 1,
      );
      if (updated) {
        const newParts = [...parts];
        newParts[i] = { ...p, parts: updated };
        return newParts;
      }
    }
    return null;
  }
  const idx = findDanglingToolIndex(parts, replacement);
  if (idx === -1) return null;
  const newParts = [...parts];
  newParts[idx] = replacement;
  return newParts;
}
