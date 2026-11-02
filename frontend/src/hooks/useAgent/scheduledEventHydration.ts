import type { Message } from "../../types";
import type { HistoryEvent } from "./types";

// Loaded details live on the message, never in a cross-account module cache.

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

export async function hydrateScheduledEvents(
  requests: HydrationRequest[],
  fetcher: HydrationFetcher,
): Promise<Map<string, HistoryEvent[]>> {
  const merged = new Map<string, HistoryEvent[]>();
  for (const { executionSessionId, runIds } of requests) {
    const uniqueIds = [...new Set(runIds)];
    for (let offset = 0; offset < uniqueIds.length; offset += RUN_IDS_CHUNK) {
      const batch = uniqueIds.slice(offset, offset + RUN_IDS_CHUNK);
      try {
        const events = await fetcher(executionSessionId, batch);
        for (const event of events) {
          const runId = event.run_id;
          if (typeof runId !== "string" || !batch.includes(runId)) continue;
          const bucket = merged.get(runId);
          if (bucket) bucket.push(event);
          else merged.set(runId, [event]);
        }
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") break;
        // Leave missing runs retryable on the next refresh.
      }
    }
  }
  return merged;
}
