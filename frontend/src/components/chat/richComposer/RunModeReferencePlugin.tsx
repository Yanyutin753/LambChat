import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { COMMAND_PRIORITY_EDITOR } from "lexical";
import { useLayoutEffect, useRef } from "react";
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

  // onToggle 来自 ChatInput 每次渲染的新闭包；走 ref 避免命令监听随按键反复注销/重注册
  const onToggleRef = useRef(onToggle);
  onToggleRef.current = onToggle;

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
          onToggleRef.current(key, false);
          return true;
        },
        COMMAND_PRIORITY_EDITOR,
      ),
    [editor],
  );

  return null;
}
