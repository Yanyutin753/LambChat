import { authFetch } from "../api/fetch";
import { API_BASE } from "../api/config";

export interface ClientSandboxDevice {
  device_id: string;
  name: string;
  platform: "tauri";
  workspace_root: string;
  last_seen_at?: string;
}

export async function listClientSandboxDevices(): Promise<
  ClientSandboxDevice[]
> {
  const response = await authFetch<{ devices: ClientSandboxDevice[] }>(
    `${API_BASE}/api/client-sandbox/devices`,
  );
  return response.devices || [];
}

export async function bindClientSandboxSession(input: {
  sessionId: string;
  deviceId: string;
  workspaceRoot: string;
}): Promise<void> {
  await authFetch(`${API_BASE}/api/client-sandbox/session-bindings`, {
    method: "POST",
    body: JSON.stringify({
      session_id: input.sessionId,
      device_id: input.deviceId,
      workspace_root: input.workspaceRoot,
    }),
  });
}

export async function enableClientSandboxPreference(input: {
  deviceId: string;
  workspaceRoot: string;
}): Promise<void> {
  await authFetch(`${API_BASE}/api/client-sandbox/preference`, {
    method: "POST",
    body: JSON.stringify({
      enabled: true,
      device_id: input.deviceId,
      workspace_root: input.workspaceRoot,
    }),
  });
}

export async function unbindClientSandboxSession(
  sessionId: string,
): Promise<void> {
  await authFetch(
    `${API_BASE}/api/client-sandbox/session-bindings/${sessionId}`,
    {
      method: "DELETE",
    },
  );
}
