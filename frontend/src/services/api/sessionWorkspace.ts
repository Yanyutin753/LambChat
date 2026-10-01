import { API_BASE } from "./config";
import { authFetch } from "./fetch";

type WorkspaceValues = Record<string, string | boolean | number>;
interface PendingWorkspace {
  values: WorkspaceValues;
  promise: Promise<unknown>;
  failed: boolean;
}
const pending = new Map<string, PendingWorkspace>();
export const WORKSPACE_OPTION_KEYS = new Set([
  "sandbox",
  "sandbox_machine_id",
  "sandbox_workspace",
]);

function persist(sessionId: string, values: WorkspaceValues): Promise<unknown> {
  const previous = pending.get(sessionId);
  const write = () =>
    authFetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({
        metadata: Object.fromEntries(
          Object.entries(values).map(([key, value]) => [
            `agent_options.${key}`,
            value,
          ]),
        ),
      }),
    });
  const promise = previous
    ? previous.promise.catch(() => {}).then(write)
    : write();
  const entry = { values, promise, failed: false };
  pending.set(sessionId, entry);
  void promise.then(
    () => {
      if (pending.get(sessionId) === entry) pending.delete(sessionId);
    },
    () => {
      entry.failed = true;
    },
  );
  return promise;
}

/** 顺序保存工作区选择；后续修改包含未成功落库的字段，防止机器/目录错配。 */
export function saveSessionWorkspaceOption(
  sessionId: string,
  key: string,
  value: string | boolean | number,
): Promise<unknown> {
  if (!WORKSPACE_OPTION_KEYS.has(key)) return Promise.resolve();
  return persist(sessionId, {
    ...pending.get(sessionId)?.values,
    [key]: value,
  });
}

/** 读取前等待落库；保存失败后的刷新会重试，绝不静默读取旧目录。 */
export async function waitForSessionWorkspace(
  sessionId: string,
): Promise<void> {
  let current;
  while ((current = pending.get(sessionId))) {
    if (current.failed) await persist(sessionId, current.values);
    else await current.promise;
  }
}
