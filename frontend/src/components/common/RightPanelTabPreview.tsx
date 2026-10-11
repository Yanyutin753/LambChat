import { useState } from "react";
import type { RightPanelEntry } from "./rightPanelCoordinator";

/** Read the already-mounted viewer; never mount another editor or activate a tab. */
function readPreview(panelId?: string) {
  const root = panelId ? document.getElementById(panelId) : null;
  if (!root) return { text: "", image: "" };
  let text = "";
  let image = "";
  const walker = document.createTreeWalker(
    root,
    NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        if (
          node instanceof Element &&
          node.matches(
            'button, input, textarea, select, script, style, [contenteditable="true"], [hidden], [aria-hidden="true"]',
          )
        )
          return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    },
  );
  let node: Node | null;
  let visited = 0;
  while (visited++ < 1200 && (node = walker.nextNode())) {
    if (node.nodeType === Node.TEXT_NODE && text.length < 600) {
      text += ` ${node.textContent ?? ""}`.slice(0, 600 - text.length);
    }
    if (
      !image &&
      node instanceof HTMLImageElement &&
      node.complete &&
      node.naturalWidth
    ) {
      image = node.currentSrc || node.src;
    }
    if (
      !image &&
      node instanceof HTMLCanvasElement &&
      node.width &&
      node.height
    ) {
      try {
        const thumbnail = document.createElement("canvas");
        const scale = Math.min(1, 320 / node.width, 180 / node.height);
        thumbnail.width = Math.max(1, Math.round(node.width * scale));
        thumbnail.height = Math.max(1, Math.round(node.height * scale));
        const context = thumbnail.getContext("2d");
        if (context) {
          context.drawImage(node, 0, 0, thumbnail.width, thumbnail.height);
          image = thumbnail.toDataURL();
        }
      } catch {
        // Cross-origin canvases can still fall back to the viewer's text/metadata.
      }
    }
    if (text.length >= 600 && image) break;
  }
  return { text: text.replace(/\s+/g, " ").trim().slice(0, 600), image };
}

export function RightPanelTabPreview({
  entry,
  label,
}: {
  entry: RightPanelEntry;
  label: string;
}) {
  // Tooltip mounts on hover/focus/long press, so this snapshot stays cheap and local.
  const [preview] = useState(() => readPreview(entry.panelId));
  return (
    <span className="right-panel-tab-details">
      <strong>{label}</strong>
      {entry.path && entry.path !== label && (
        <span className="right-panel-tab-path">{entry.path}</span>
      )}
      {preview.image && (
        <img
          className="right-panel-tab-preview-image"
          src={preview.image}
          alt=""
        />
      )}
      {preview.text && (
        <span className="right-panel-tab-preview-text">{preview.text}</span>
      )}
      {entry.fileType && (
        <span className="right-panel-tab-type">{entry.fileType}</span>
      )}
    </span>
  );
}
