import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import {
  WORKSPACE_OPTION_KEYS,
  workspaceOptionPatch,
} from "../../components/chat/workspaceSelection";

type WorkspaceValues = Record<string, string | boolean | number>;
interface PendingWorkspace {
  values: WorkspaceValues;
  promise: Promise<unknown>;
  failed: boolean;
}
const pending = new Map<string, PendingWorkspace>();
export { WORKSPACE_OPTION_KEYS } from "../../components/chat/workspaceSelection";

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
  return saveSessionWorkspaceOptions(
    sessionId,
    workspaceOptionPatch(key, value),
  );
}

export function saveSessionWorkspaceOptions(
  sessionId: string,
  values: WorkspaceValues,
): Promise<unknown> {
  const workspace = Object.fromEntries(
    Object.entries(values).filter(([key]) => WORKSPACE_OPTION_KEYS.has(key)),
  );
  if (!Object.keys(workspace).length) return Promise.resolve();
  return persist(sessionId, {
    ...pending.get(sessionId)?.values,
    ...workspace,
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
