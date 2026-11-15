import { registerPlugin, type PluginListenerHandle } from "@capacitor/core";

export interface PhoneControlState {
  connected: boolean;
  accessibility: boolean;
  paused: boolean;
  display: number;
  backgroundSupported: boolean;
}

export interface OverlayContext {
  scope: string;
  ready: boolean;
  running: boolean;
  approvalId: string;
  message: string;
  canApprove: boolean;
}
interface LocalDevicePlugin {
  addListener(
    event: "overlayAction",
    listener: (event: {
      id: string;
      scope: string;
      action: string;
      text?: string;
      approvalId?: string;
      message?: string;
    }) => void,
  ): Promise<PluginListenerHandle>;
  setOverlayContext(options: OverlayContext): Promise<void>;
  clearOverlayContext(options: { scope: string }): Promise<void>;
  overlayResult(options: { id: string; accepted: boolean }): Promise<void>;

  phoneDiscover(): Promise<{ pairing: number[]; connect: number[] }>;
  phoneState(): Promise<PhoneControlState>;
  phonePair(options: { port: number; code: string }): Promise<void>;
  phoneConnect(options: {
    port: number;
    background: boolean;
  }): Promise<PhoneControlState>;
  phoneAction(options: {
    action:
      | "accessibility"
      | "debugging"
      | "pause"
      | "resume"
      | "takeover"
      | "disconnect";
  }): Promise<PhoneControlState | undefined>;

  overlayStatus(): Promise<{ enabled: boolean; granted: boolean }>;
  setOverlayEnabled(options: {
    enabled: boolean;
  }): Promise<{ enabled: boolean; granted: boolean }>;
  invoke(options: {
    command: string;
    args?: Record<string, unknown>;
  }): Promise<{ value?: unknown } | undefined>;
  importFile(): Promise<{ name?: string } | undefined>;
  listFiles(): Promise<{ files: { name: string; size: number }[] }>;
  exportFile(options: { name: string }): Promise<void>;
}

export const LocalDevice = registerPlugin<LocalDevicePlugin>("LocalDevice");

/** Gate on the actual bridge: older APKs and iOS must never mint an unusable PAT. */
export function isAndroidLocalDevice(): boolean {
  const capacitor = (
    globalThis as {
      Capacitor?: {
        isNativePlatform?: () => boolean;
        getPlatform?: () => string;
        isPluginAvailable?: (name: string) => boolean;
      };
    }
  ).Capacitor;
  return (
    capacitor?.isNativePlatform?.() === true &&
    capacitor.getPlatform?.() === "android" &&
    capacitor.isPluginAvailable?.("LocalDevice") === true
  );
}

export async function invokeAndroidDevice<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  const result = await LocalDevice.invoke({ command, args });
  return result?.value as T;
}
