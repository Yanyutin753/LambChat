import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import type { EditorView } from "@codemirror/view";
import { openSearchPanel } from "@codemirror/search";
import { ToolbarIconButton } from "./ui/ToolbarIconButton";
import { CopyButton } from "./CopyButton";
import "../../i18n/codeEditor";
import "../../styles/code-editor.css";

export function CodeMirrorSearchToolbar({
  viewRef,
  copyText,
}: {
  viewRef: RefObject<EditorView | null>;
  copyText?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="code-editor-toolbar">
      <ToolbarIconButton
        icon={<Search size={14} aria-hidden="true" />}
        aria-label={t("common.search")}
        title={t("common.search")}
        onClick={() => {
          const view = viewRef.current;
          if (!view) return;
          openSearchPanel(view);
          view.dom
            .querySelector<HTMLInputElement>('.cm-search [name="search"]')
            ?.focus();
        }}
      />
      {copyText !== undefined && <CopyButton text={copyText} />}
    </div>
  );
}
