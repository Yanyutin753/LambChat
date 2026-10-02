import type { ReactNode, RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import type { EditorView } from "@codemirror/view";
import { openCodeMirrorSearch } from "./codeMirrorSearchExtensions";
import { IconButton } from "./ui/IconButton";
import { CopyButton } from "./CopyButton";
import "../../i18n/codeEditor";
import "../../styles/code-editor.css";

export function CodeMirrorSearchToolbar({
  viewRef,
  copyText,
  copyLabel,
  label,
}: {
  viewRef: RefObject<EditorView | null>;
  copyText?: string;
  copyLabel?: string;
  label?: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="code-editor-toolbar">
      {label && <div className="min-w-0 flex-1">{label}</div>}
      <IconButton
        size="sm"
        icon={<Search size={14} aria-hidden="true" />}
        aria-label={t("common.search")}
        title={t("common.search")}
        onClick={(event) => {
          event.stopPropagation();
          openCodeMirrorSearch(viewRef.current?.dom ?? null);
        }}
      />
      {copyText !== undefined && (
        <CopyButton text={copyText} label={copyLabel} />
      )}
    </div>
  );
}
