import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { mergeRegister } from "@lexical/utils";
import {
  $getNodeByKey,
  $getSelection,
  $isRangeSelection,
  $isTextNode,
  COMMAND_PRIORITY_HIGH,
  KEY_ARROW_DOWN_COMMAND,
  KEY_ARROW_UP_COMMAND,
  KEY_ENTER_COMMAND,
  KEY_ESCAPE_COMMAND,
  KEY_TAB_COMMAND,
  type NodeKey,
} from "lexical";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SlashDropdownMenu } from "../SlashDropdownMenu";
import {
  CHAT_INPUT_SLASH_COMMANDS,
  getSlashDropdownSections,
  type ChatInputSlashCommand,
  type SlashDropdownItem,
} from "../chatInputSlashCommands";
import type { AvailableComposerSkill } from "./RichChatComposer";
import { INSERT_SKILL_REFERENCE_COMMAND } from "./nodes/referenceCommands";
import { findSlashTrigger, getSlashTokenId } from "./slashTrigger";

interface SlashCommandContext {
  nodeKey: NodeKey;
  from: number;
  to: number;
  query: string;
  tokenId: string;
  anchorRect: DOMRect | null;
}

interface SlashCommandPluginProps {
  availableSkills: readonly AvailableComposerSkill[];
  enabledSkillNames: readonly string[];
  containerRef: React.RefObject<HTMLDivElement | null>;
  onApplyCommand?: (command: ChatInputSlashCommand) => void;
}

function getCaretRect(): DOMRect | null {
  const domSelection = window.getSelection();
  if (!domSelection || domSelection.rangeCount === 0) return null;
  const range = domSelection.getRangeAt(0);
  return typeof range.getBoundingClientRect === "function"
    ? range.getBoundingClientRect()
    : null;
}

export function SlashCommandPlugin({
  availableSkills,
  enabledSkillNames,
  containerRef,
  onApplyCommand,
}: SlashCommandPluginProps) {
  const [editor] = useLexicalComposerContext();
  const [context, setContext] = useState<SlashCommandContext | null>(null);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const dismissedTokenRef = useRef<string | null>(null);

  const items = useMemo<SlashDropdownItem[]>(() => {
    if (!context) return [];
    const query = context.query.toLowerCase();
    const matches: SlashDropdownItem[] = [];
    for (const command of CHAT_INPUT_SLASH_COMMANDS) {
      if (command.command.slice(1).startsWith(query)) {
        matches.push({ type: "command", command });
      }
    }
    for (const skill of availableSkills) {
      if (skill.name.toLowerCase().startsWith(query)) {
        matches.push({ type: "skill", skill });
      }
    }
    return matches;
  }, [availableSkills, context]);

  const sections = useMemo(() => getSlashDropdownSections(items), [items]);
  const open = context !== null && items.length > 0;

  useEffect(() => {
    return editor.registerUpdateListener(({ editorState }) => {
      const nextContext = editorState.read<SlashCommandContext | null>(() => {
        const selection = $getSelection();
        if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
          dismissedTokenRef.current = null;
          return null;
        }
        const anchorNode = selection.anchor.getNode();
        if (!$isTextNode(anchorNode)) {
          dismissedTokenRef.current = null;
          return null;
        }
        const caretOffset = selection.anchor.offset;
        const text = anchorNode.getTextContent();
        const trigger = findSlashTrigger(text, caretOffset);
        if (!trigger) {
          dismissedTokenRef.current = null;
          return null;
        }
        const tokenId = getSlashTokenId(
          anchorNode.getKey(),
          text,
          trigger.from,
        );
        if (dismissedTokenRef.current === tokenId) return null;
        dismissedTokenRef.current = null;
        return {
          nodeKey: anchorNode.getKey(),
          ...trigger,
          tokenId,
          anchorRect: getCaretRect(),
        };
      });
      setContext((current) =>
        current?.tokenId === nextContext?.tokenId &&
        current?.to === nextContext?.to
          ? current
          : nextContext,
      );
    });
  }, [editor]);

  const applySelection = useCallback(
    (item: SlashDropdownItem) => {
      if (!context) return;
      editor.update(
        () => {
          const node = $getNodeByKey(context.nodeKey);
          if (!$isTextNode(node)) return;
          const range = node.select(context.from, context.to);
          range.removeText();
          if (item.type === "skill") {
            editor.dispatchCommand(INSERT_SKILL_REFERENCE_COMMAND, {
              skillName: item.skill.name,
              tags: item.skill.tags,
            });
          } else if (item.command.kind === "insert") {
            range.insertText(`${item.command.command} `);
          }
        },
        { discrete: true },
      );
      if (item.type === "command") onApplyCommand?.(item.command);
      dismissedTokenRef.current = null;
      setContext(null);
    },
    [context, editor, onApplyCommand],
  );

  const dismissMenu = useCallback(() => {
    if (!context) return;
    dismissedTokenRef.current = context.tokenId;
    setContext(null);
  }, [context]);

  useEffect(() => {
    const moveHighlight = (delta: number, event: KeyboardEvent) => {
      if (!open) return false;
      event.preventDefault();
      setHighlightIndex(
        (current) => (current + delta + items.length) % items.length,
      );
      return true;
    };
    const choose = (event: KeyboardEvent | null) => {
      if (!open || !event) return false;
      if (event.isComposing || event.keyCode === 229) return false;
      event.preventDefault();
      const item = items[highlightIndex];
      if (item) applySelection(item);
      return item !== undefined;
    };
    return mergeRegister(
      editor.registerCommand(
        KEY_ARROW_DOWN_COMMAND,
        (event) => moveHighlight(1, event),
        COMMAND_PRIORITY_HIGH,
      ),
      editor.registerCommand(
        KEY_ARROW_UP_COMMAND,
        (event) => moveHighlight(-1, event),
        COMMAND_PRIORITY_HIGH,
      ),
      editor.registerCommand(KEY_ENTER_COMMAND, choose, COMMAND_PRIORITY_HIGH),
      editor.registerCommand(KEY_TAB_COMMAND, choose, COMMAND_PRIORITY_HIGH),
      editor.registerCommand(
        KEY_ESCAPE_COMMAND,
        (event) => {
          if (!open || !context) return false;
          event.preventDefault();
          dismissMenu();
          return true;
        },
        COMMAND_PRIORITY_HIGH,
      ),
    );
  }, [
    applySelection,
    context,
    dismissMenu,
    editor,
    highlightIndex,
    items,
    open,
  ]);

  return (
    <>
      <SlashDropdownMenu
        open={open}
        sections={sections}
        items={items}
        runSkillNameSet={new Set(enabledSkillNames)}
        containerRef={containerRef}
        anchorRect={context?.anchorRect ?? null}
        onApplySelection={applySelection}
        onDismiss={dismissMenu}
        highlightIndex={highlightIndex}
        onHighlightChange={setHighlightIndex}
      />
      <span className="sr-only" aria-live="polite">
        {open ? `${items.length} slash commands available` : ""}
      </span>
    </>
  );
}
