const PLUGIN_RUNTIME_UPDATED_EVENT = "lambchat:plugin-runtime-updated";

export function dispatchPluginRuntimeUpdated(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(PLUGIN_RUNTIME_UPDATED_EVENT));
}

export function listenPluginRuntimeUpdated(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(PLUGIN_RUNTIME_UPDATED_EVENT, listener);
  return () => window.removeEventListener(PLUGIN_RUNTIME_UPDATED_EVENT, listener);
}
