let currentOwner: symbol | null = null;
let currentClose: (() => void) | null = null;

export function closeCurrentToolPanel() {
  if (currentClose) {
    console.log("[ToolPanelRegistry] closing current panel", {
      owner: currentOwner?.description ?? String(currentOwner),
    });
    currentClose();
    currentClose = null;
    currentOwner = null;
  }
}

export function registerToolPanel(
  owner: symbol,
  close: () => void,
): () => void {
  console.log("[ToolPanelRegistry] register panel", {
    owner: owner.description ?? String(owner),
    currentOwner: currentOwner?.description ?? String(currentOwner),
  });
  if (currentOwner !== owner) {
    closeCurrentToolPanel();
  }

  currentOwner = owner;
  currentClose = close;

  return () => {
    if (currentOwner === owner) {
      console.log("[ToolPanelRegistry] cleanup current panel", {
        owner: owner.description ?? String(owner),
      });
      currentOwner = null;
      currentClose = null;
    }
  };
}

export function clearToolPanelRegistry() {
  currentOwner = null;
  currentClose = null;
}
