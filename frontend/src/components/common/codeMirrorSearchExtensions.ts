import type { TFunction } from "i18next";
import { EditorState } from "@codemirror/state";
import { openSearchPanel, search } from "@codemirror/search";
import { EditorView } from "@codemirror/view";
import type { KeyboardEvent } from "react";

export function openCodeMirrorSearch(editor: HTMLElement | null) {
  if (!editor?.isConnected) return;
  const view = EditorView.findFromDOM(editor);
  if (!view) return;
  openSearchPanel(view);
  view.dom
    .querySelector<HTMLInputElement>('.cm-search [name="search"]')
    ?.focus();
}

export function guardCodeMirrorSearchComposition(event: KeyboardEvent) {
  if (
    (event.nativeEvent.isComposing || event.keyCode === 229) &&
    (event.key === "Escape" || event.key === "Enter") &&
    event.target instanceof Element &&
    event.target.closest(".cm-search")
  )
    event.stopPropagation();
}

export function codeMirrorSearchExtensions(t: TFunction) {
  return [
    search({ top: true }),
    EditorState.phrases.of({
      Find: t("codeEditor.find"),
      Replace: t("codeEditor.replace"),
      next: t("codeEditor.next"),
      previous: t("codeEditor.previous"),
      all: t("common.selectAll"),
      "match case": t("codeEditor.matchCase"),
      regexp: t("codeEditor.regexp"),
      "by word": t("codeEditor.wholeWord"),
      replace: t("codeEditor.replace"),
      "replace all": t("codeEditor.replaceAll"),
      close: t("common.close"),
      "Go to line": t("codeEditor.goToLine"),
      go: t("codeEditor.go"),
      "current match": t("codeEditor.currentMatch"),
      "on line": t("codeEditor.onLine"),
      "replaced match on line $": t("codeEditor.replacedMatch"),
      "replaced $ matches": t("codeEditor.replacedMatches"),
    }),
  ];
}
