import type { Message, MessagePart } from "../../../types";
import type { RevealFileImageInfo } from "./revealFileImageUtils";

/**
 * 已完成 run 的"收尾"展示（对齐 Codex 终端行为）：
 * 中间过程（思考/工具/产物卡片等）折叠成一行摘要，仅保留
 * 最后一段 output_text 与其后的收尾部分可见。
 */

export type RunPartGroup =
  | {
      type: "gallery";
      images: RevealFileImageInfo[];
      startPartIndex: number;
    }
  | { type: "single"; part: MessagePart; partIndex: number };

/**
 * 将分组后的 parts 切成 head（可折叠的中间过程）与 tail（始终可见的收尾）。
 * tail 从最后一个 text part（最终 output_text）开始，包含其后的所有分组；
 * 若没有任何 text part，则只有末尾连续的 cancelled 分组保留可见。
 */
export function splitRunTailGroups<T extends RunPartGroup>(
  groups: T[],
  opts: { enabled: boolean },
): { head: T[]; tail: T[] } {
  if (!opts.enabled) {
    return { head: [], tail: groups };
  }

  let lastTextIndex = -1;
  for (let i = groups.length - 1; i >= 0; i--) {
    const group = groups[i];
    if (group.type === "single" && group.part.type === "text") {
      lastTextIndex = i;
      break;
    }
  }

  if (lastTextIndex >= 0) {
    return {
      head: groups.slice(0, lastTextIndex),
      tail: groups.slice(lastTextIndex),
    };
  }

  let tailStart = groups.length;
  while (tailStart > 0) {
    const group = groups[tailStart - 1];
    if (group.type !== "single" || group.part.type !== "cancelled") break;
    tailStart--;
  }

  return { head: groups.slice(0, tailStart), tail: groups.slice(tailStart) };
}

/** 折叠摘要中统计的"步骤"类型（不含不可见锚点与纯文本）。 */
const RUN_STEP_PART_TYPES = new Set([
  "tool",
  "thinking",
  "sandbox",
  "subagent",
  "todo",
  "summary",
]);

export function countRunSteps(parts: MessagePart[]): number {
  return parts.filter((part) => RUN_STEP_PART_TYPES.has(part.type)).length;
}

/** Codex 风格的紧凑时长：45s / 1m 30s / 1h 02m 05s。 */
export function formatElapsedCompact(totalSeconds: number): string {
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  if (totalSeconds < 3600) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(
    seconds,
  ).padStart(2, "0")}s`;
}

function toMs(value: string | number | undefined): number | null {
  if (value === undefined) return null;
  const ms = typeof value === "number" ? value : Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

interface PartTimestamps {
  startedAt?: string | number;
  completedAt?: string | number;
}

function collectPartTimes(part: MessagePart, times: number[]): void {
  const { startedAt, completedAt } = part as unknown as PartTimestamps;
  const start = toMs(startedAt);
  const end = toMs(completedAt);
  if (start !== null) times.push(start);
  if (end !== null) times.push(end);
  if (part.type === "subagent" && part.parts) {
    for (const nested of part.parts) collectPartTimes(nested, times);
  }
}

/**
 * 计算 run 总时长：优先 message.duration（token:usage / 历史加载写入），
 * 否则用 parts 中最早 startedAt 与最晚 completedAt 推算。
 */
export function getRunElapsedMs(
  message: Pick<Message, "duration" | "parts">,
): number | null {
  if (typeof message.duration === "number" && message.duration > 0) {
    return message.duration;
  }

  const times: number[] = [];
  for (const part of message.parts ?? []) collectPartTimes(part, times);
  if (times.length === 0) return null;

  const elapsed = Math.max(...times) - Math.min(...times);
  return elapsed > 0 ? elapsed : null;
}

/**
 * run 起点（流式期间实时计时的锚点）：
 * parts 中最早的时间戳，缺省回退到 message.timestamp。
 */
export function getRunStartedAtMs(
  message: Pick<Message, "timestamp" | "parts">,
): number | null {
  const times: number[] = [];
  for (const part of message.parts ?? []) collectPartTimes(part, times);
  if (times.length > 0) return Math.min(...times);
  const timestampMs = message.timestamp?.getTime();
  if (typeof timestampMs === "number" && Number.isFinite(timestampMs)) {
    return timestampMs;
  }
  return null;
}
