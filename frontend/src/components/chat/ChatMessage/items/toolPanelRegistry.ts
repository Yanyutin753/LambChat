let currentOwner: symbol | null = null;
let currentClose: (() => void) | null = null;
let currentRegistryKey: string | null = null;

export function closeCurrentToolPanel() {
  if (currentClose) {
    currentClose();
    currentClose = null;
    currentOwner = null;
    currentRegistryKey = null;
  }
}

export function registerToolPanel(
  owner: symbol,
  close: () => void,
  registryKey?: string,
): () => void {
  const isSameLogicalPanel =
    !!registryKey && !!currentRegistryKey && currentRegistryKey === registryKey;

  if (currentOwner !== owner && !isSameLogicalPanel) {
    closeCurrentToolPanel();
  }

  currentOwner = owner;
  currentClose = close;
  currentRegistryKey = registryKey ?? null;

  return () => {
    if (currentOwner === owner) {
      currentOwner = null;
      currentClose = null;
      currentRegistryKey = null;
    }
  };
}

export function clearToolPanelRegistry() {
  currentOwner = null;
  currentClose = null;
  currentRegistryKey = null;
}
