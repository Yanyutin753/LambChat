import { useSyncExternalStore } from "react";

export type UpdateChannel = "stable" | "dev";
const KEY = "lambchat:update-channel";
export const UPDATE_CHANNEL_CHANGED = "lambchat:update-channel-changed";
let revision = 0;
let busy = false;
let fallback: UpdateChannel = "stable";
let sessionOnly = false;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
const notify = () => listeners.forEach((listener) => listener());
export function getUpdateChannel(): UpdateChannel {
  if (sessionOnly) return fallback;
  try {
    return localStorage.getItem(KEY) === "dev" ? "dev" : "stable";
  } catch {
    return fallback;
  }
}
export const getUpdateRevision = () => revision;
export function setUpdateBusy(value: boolean): void {
  busy = value;
  notify();
}
export function setUpdateChannel(channel: UpdateChannel): boolean {
  if (busy) return false;
  if (channel === getUpdateChannel()) return true;
  fallback = channel;
  try {
    localStorage.setItem(KEY, channel);
    sessionOnly = false;
  } catch {
    sessionOnly = true;
  }
  revision++;
  notify();
  window.dispatchEvent(new Event(UPDATE_CHANNEL_CHANGED));
  return true;
}
export function useUpdateChannel() {
  const channel = useSyncExternalStore(
    subscribe,
    getUpdateChannel,
    () => "stable" as const,
  );
  const isBusy = useSyncExternalStore(
    subscribe,
    () => busy,
    () => false,
  );
  return { channel, busy: isBusy };
}
