import type { ComponentProps } from "react";
import { EditorSidebar } from "../common/EditorSidebar";
import type { Dialog } from "../common/Dialog";

// Keep the same actions and loading state in the workspace and chat shortcuts.
export function AssistantSurface({
  embedded = false,
  ...props
}: ComponentProps<typeof Dialog> & { embedded?: boolean }) {
  if (!embedded)
    return (
      <EditorSidebar
        open={props.open}
        onClose={() => {
          if (props.dismissible !== false) props.onClose();
        }}
        title={typeof props.title === "string" ? props.title : ""}
        footer={
          <div className="flex flex-wrap items-center justify-end gap-2">
            {props.footer}
          </div>
        }
      >
        <div className="es-form">{props.children}</div>
      </EditorSidebar>
    );
  return (
    <section
      className="assistant-workspace-surface"
      aria-label={typeof props.title === "string" ? props.title : undefined}
    >
      <div className="panel-body overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl py-4 sm:py-5">
          {props.children}
        </div>
      </div>
      <div className="panel-pagination">
        <div className="assistant-workspace-footer mx-auto flex w-full max-w-3xl flex-wrap items-center justify-end gap-2">
          {props.footer}
        </div>
      </div>
    </section>
  );
}
