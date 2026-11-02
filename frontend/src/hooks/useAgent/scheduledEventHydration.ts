import type { Message } from "../../types";
import type { HistoryEvent } from "./types";

/**
 * 定时结果卡片的执行事件补全：按执行会话分组的批量拉取 + 模块级缓存。
 *
 * 最终 run 的事件不可变，缓存无需 TTL；in-flight 去重避免同屏重复请求。
 * 解决旧实现「每张卡片一个请求、串行、重进对话全部重拉」的问题。
 */

/** 单个批量请求携带的 run 数上限（控制 URL 长度） */
const RUN_IDS_CHUNK = 50;

export interface HydrationRequest {
  executionSessionId: string;
  runIds: string[];
}

export type HydrationFetcher = (
  executionSessionId: string,
  runIds: string[],
) => Promise<HistoryEvent[]>;

export function groupPendingHydrations(
  messages: Message[],
): HydrationRequest[] {
  const bySource = new Map<string, string[]>();
  for (const message of messages) {
    const metadata = message.metadata ?? {};
    if (metadata.scheduledFinal !== true) continue;
    if (metadata.scheduledEventsLoaded === true) continue;
    const source = metadata.scheduledExecutionSessionId;
    const runId = message.runId;
    if (
      typeof source !== "string" ||
      !runId ||
      typeof metadata.scheduledTaskId !== "string" ||
      typeof metadata.scheduledTaskName !== "string"
    ) {
      continue;
    }
    const runIds = bySource.get(source);
    if (runIds) runIds.push(runId);
    else bySource.set(source, [runId]);
  }
  return Array.from(bySource, ([executionSessionId, runIds]) => ({
    executionSessionId,
    runIds,
  }));
}

const cachedEvents = new Map<string, HistoryEvent[]>();
const inflight = new Map<string, Promise<Map<string, HistoryEvent[]>>>();

export function resetScheduledHydrationCache() {
  cachedEvents.clear();
  inflight.clear();
}

function chunk<T>(items: T[], size: number): T[][] {
  const groups: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    groups.push(items.slice(index, index + size));
  }
  return groups;
}

function fetchSourceBatch(
  executionSessionId: string,
  runIds: string[],
  fetcher: HydrationFetcher,
): Promise<Map<string, HistoryEvent[]>> {
  const key = `${executionSessionId}|${[...runIds].sort().join(",")}`;
  const existing = inflight.get(key);
  if (existing) return existing;
  const promise = fetcher(executionSessionId, runIds)
    .then((events) => {
      const byRun = new Map<string, HistoryEvent[]>();
      for (const event of events) {
        const runId = event.run_id;
        if (typeof runId !== "string") continue;
        const bucket = byRun.get(runId);
        if (bucket) bucket.push(event);
        else byRun.set(runId, [event]);
      }
      for (const runId of runIds) {
        const events = byRun.get(runId) ?? [];
        byRun.set(runId, events);
        cachedEvents.set(runId, events);
      }
      return byRun;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, promise);
  return promise;
}

export async function hydrateScheduledEvents(
  requests: HydrationRequest[],
  fetcher: HydrationFetcher,
): Promise<Map<string, HistoryEvent[]>> {
  const merged = new Map<string, HistoryEvent[]>();
  for (const { executionSessionId, runIds } of requests) {
    const missing: string[] = [];
    for (const runId of runIds) {
      const events = cachedEvents.get(runId);
      if (events) merged.set(runId, events);
      else missing.push(runId);
    }
    const batches = chunk(missing, RUN_IDS_CHUNK);
    const results = await Promise.all(
      batches.map((batch) =>
        fetchSourceBatch(executionSessionId, batch, fetcher).catch(
          () => new Map<string, HistoryEvent[]>(),
        ),
      ),
    );
    for (const byRun of results) {
      for (const [runId, events] of byRun) {
        merged.set(runId, events);
      }
    }
  }
  return merged;
}
