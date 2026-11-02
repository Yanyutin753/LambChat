import { useEffect } from "react";
import { useSyncExternalStore } from "react";
import { createSingletonStore } from "../components/chat/ChatMessage/items/createSingletonStore";
import { scheduledTaskApi } from "../services/api/scheduledTask";

/**
 * 定时任务提示词缓存：旧 scheduled:result 载荷没有 prompt 字段，
 * 气泡渲染时按 taskId 懒加载任务设置里的提示词兜底。
 * 每任务只取一次；已确认无提示词或加载失败不重复打接口（失败下次重试）。
 */

const store = createSingletonStore<Record<string, string>>({});

const inflightByTask = new Map<string, Promise<void>>();
const attempted = new Set<string>();

export function getScheduledTaskPromptState(): Record<string, string> {
  return store.get();
}

export function subscribeScheduledTaskPrompts(listener: () => void) {
  return store.subscribe(listener);
}

export function useScheduledTaskPrompt(
  taskId: string | undefined,
): string | undefined {
  const prompts = useSyncExternalStore(
    subscribeScheduledTaskPrompts,
    getScheduledTaskPromptState,
  );
  useEffect(() => {
    if (taskId) void ensureScheduledTaskPrompt(taskId);
  }, [taskId]);
  return taskId ? prompts[taskId] : undefined;
}

export async function ensureScheduledTaskPrompt(taskId: string): Promise<void> {
  if (attempted.has(taskId) || inflightByTask.has(taskId)) {
    return inflightByTask.get(taskId) ?? Promise.resolve();
  }
  const inflight = (async () => {
    try {
      const task = await scheduledTaskApi.get(taskId);
      const payload = task.input_payload ?? {};
      const prompt = payload.message ?? payload.prompt;
      if (typeof prompt === "string" && prompt.trim()) {
        store.set({ ...store.get(), [taskId]: prompt });
      }
      attempted.add(taskId);
    } catch {
      // 查询失败不标记 attempted，下次再试
    } finally {
      inflightByTask.delete(taskId);
    }
  })();
  inflightByTask.set(taskId, inflight);
  return inflight;
}

export function resetScheduledTaskPromptStoreForTests() {
  store.set({});
  inflightByTask.clear();
  attempted.clear();
}
