let currentOwner: symbol | null = null;
let currentClose: (() => void) | null = null;

export function closeCurrentToolPanel() {
  if (currentClose) {
    currentClose();
    currentClose = null;
    currentOwner = null;
  }
}

export function registerToolPanel(
  owner: symbol,
  close: () => void,
): () => void {
  if (currentOwner !== owner) {
    closeCurrentToolPanel();
  }

  currentOwner = owner;
  currentClose = close;

  return () => {
    if (currentOwner === owner) {
      currentOwner = null;
      currentClose = null;
    }
  };
}

export function clearToolPanelRegistry() {
  currentOwner = null;
  currentClose = null;
}
