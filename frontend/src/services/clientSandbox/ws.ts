import { invoke } from "@tauri-apps/api/core";
import { buildWebSocketUrl } from "../api/config";
import { getValidAccessToken } from "../api/tokenManager";
import {
  getClientSandboxWorkspaceRoot,
  getOrCreateClientSandboxDeviceId,
  shouldStartClientSandboxService,
} from "./device";
import type {
  ClientSandboxRegisterMessage,
  ClientSandboxRequestMessage,
  ClientSandboxResponseMessage,
} from "./types";

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

function buildRegistration(): ClientSandboxRegisterMessage {
  return {
    type: "client_sandbox:register",
    device_id: getOrCreateClientSandboxDeviceId(),
    name:
      typeof navigator !== "undefined"
        ? `LambChat Desktop (${navigator.platform || "desktop"})`
        : "LambChat Desktop",
    platform: "tauri",
    os: typeof navigator !== "undefined" ? navigator.platform || "" : "",
    app_version: "2.5.3",
    workspace_root: getClientSandboxWorkspaceRoot() || "~/LambChatWorkspace",
    capabilities: {
      execute: true,
      read_file: true,
      write_file: true,
      list: true,
    },
  };
}

async function handleRequest(
  message: ClientSandboxRequestMessage,
): Promise<ClientSandboxResponseMessage> {
  const workspaceRoot =
    getClientSandboxWorkspaceRoot() || "~/LambChatWorkspace";
  try {
    if (message.operation === "execute") {
      const result = await invoke<Record<string, unknown>>(
        "client_sandbox_execute",
        {
          workspaceRoot,
          command: String(message.payload.command || ""),
          cwd:
            typeof message.payload.cwd === "string"
              ? message.payload.cwd
              : undefined,
          timeoutSeconds: message.timeout_seconds,
        },
      );
      return {
        type: "client_sandbox:response",
        request_id: message.request_id,
        ok: true,
        result,
      };
    }
    if (message.operation === "read_file") {
      const result = await invoke<Record<string, unknown>>(
        "client_sandbox_read_file",
        {
          workspaceRoot,
          path: String(message.payload.path || ""),
          limit:
            typeof message.payload.limit === "number"
              ? message.payload.limit
              : undefined,
        },
      );
      return {
        type: "client_sandbox:response",
        request_id: message.request_id,
        ok: true,
        result,
      };
    }
    if (message.operation === "write_file") {
      const result = await invoke<Record<string, unknown>>(
        "client_sandbox_write_file",
        {
          workspaceRoot,
          path: String(message.payload.path || ""),
          content: String(message.payload.content || ""),
        },
      );
      return {
        type: "client_sandbox:response",
        request_id: message.request_id,
        ok: true,
        result,
      };
    }
    if (message.operation === "list") {
      const result = await invoke<Record<string, unknown>>(
        "client_sandbox_list",
        {
          workspaceRoot,
          path:
            typeof message.payload.path === "string"
              ? message.payload.path
              : undefined,
        },
      );
      return {
        type: "client_sandbox:response",
        request_id: message.request_id,
        ok: true,
        result,
      };
    }
    return {
      type: "client_sandbox:response",
      request_id: message.request_id,
      ok: false,
      error: {
        code: "unsupported_operation",
        message: `Unsupported client sandbox operation: ${message.operation}`,
      },
    };
  } catch (error) {
    return {
      type: "client_sandbox:response",
      request_id: message.request_id,
      ok: false,
      error: {
        code: "client_execution_error",
        message: error instanceof Error ? error.message : String(error),
      },
    };
  }
}

export async function startClientSandboxService(): Promise<void> {
  if (!shouldStartClientSandboxService()) return;
  if (socket && socket.readyState <= WebSocket.OPEN) return;

  const token = await getValidAccessToken();
  if (!token) return;

  const wsUrl = new URL(
    buildWebSocketUrl("/api/client-sandbox/ws/client-sandbox"),
  );
  wsUrl.searchParams.set("token", token);
  const ws = new WebSocket(wsUrl.toString());
  socket = ws;

  ws.onmessage = (event) => {
    void (async () => {
      const message = JSON.parse(event.data);
      if (message.type === "auth:ok") {
        ws.send(JSON.stringify(buildRegistration()));
        return;
      }
      if (message.type === "client_sandbox:request") {
        const response = await handleRequest(message);
        ws.send(JSON.stringify(response));
      }
    })();
  };

  ws.onclose = () => {
    socket = null;
    if (reconnectTimer === null) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void startClientSandboxService();
      }, 5000);
    }
  };
}
