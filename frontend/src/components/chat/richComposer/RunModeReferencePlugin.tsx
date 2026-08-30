import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { COMMAND_PRIORITY_EDITOR } from "lexical";
import { useLayoutEffect } from "react";
import type { RunModesOptions } from "./composerTypes";
import { $reconcileRunModeChips } from "./nodes/RunModeReferenceNode";
import { TOGGLE_RUN_MODE_COMMAND } from "./nodes/referenceCommands";

export function RunModeReferencePlugin({
  runModes,
}: {
  runModes: RunModesOptions;
}) {
  const [editor] = useLexicalComposerContext();
  const { autoEnabled, goalEnabled, onToggle } = runModes;

  useLayoutEffect(() => {
    editor.update(
      () => $reconcileRunModeChips({ auto: autoEnabled, goal: goalEnabled }),
      { discrete: true },
    );
  }, [editor, autoEnabled, goalEnabled]);

  useLayoutEffect(
    () =>
      editor.registerCommand(
        TOGGLE_RUN_MODE_COMMAND,
        (key) => {
          onToggle(key, false);
          return true;
        },
        COMMAND_PRIORITY_EDITOR,
      ),
    [editor, onToggle],
  );

  return null;
}
