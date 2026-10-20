import { EditorView } from "@codemirror/view";

export function codeMirrorCspNonce() {
  // Tauri authorizes the boot style; dynamic editor styles need the same nonce.
  const nonce = document.getElementById("lambchat-boot-styles")?.nonce;
  return EditorView.cspNonce.of(nonce || "");
}
