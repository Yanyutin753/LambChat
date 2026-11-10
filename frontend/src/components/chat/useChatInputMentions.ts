import { useCallback, useEffect, useState } from "react";
import { useMentionState } from "../../hooks/useMentionState";
import { useMentionSearch } from "../../hooks/useMentionSearch";
import { useTeamMentionSearch } from "../../hooks/useTeamMentionSearch";
import {
  useAssistantGroupMembers,
  type GroupMember,
} from "../assistants/AssistantGroupContext";
import type { ChatInputProps } from "./chatInputTypes";

export function useChatInputMentions({
  input,
  cursorPosition,
  mentionMode,
  onSelectTeam,
  onUsePersonaPreset,
  onMentionQueryChange,
  selectedPersonaPresetId,
  selectedTeamId,
  setComposerPlainText,
  setCursorPosition,
  focusComposerAtEnd,
}: Pick<
  ChatInputProps,
  | "onSelectTeam"
  | "onUsePersonaPreset"
  | "onMentionQueryChange"
  | "selectedPersonaPresetId"
  | "selectedTeamId"
> & {
  input: string;
  cursorPosition: number;
  mentionMode: "team" | "persona";
  setComposerPlainText: (text: string) => void;
  setCursorPosition: (position: number) => void;
  focusComposerAtEnd: () => void;
}) {
  const groupMembers = useAssistantGroupMembers();
  const [selectedMentionInput, setSelectedMentionInput] = useState<
    string | null
  >(null);
  const mentionEnabled =
    groupMembers !== null ||
    (mentionMode === "team" ? !!onSelectTeam : !!onUsePersonaPreset);
  const {
    mention,
    moveHighlight: moveMentionHighlight,
    setHighlightedIndex: setMentionHighlight,
    setResultCount: setMentionResultCount,
    resetMention,
    dismissMention,
  } = useMentionState(input, cursorPosition, mentionEnabled);
  const mentionSearch = useMentionSearch(
    mention.query,
    mention.isActive && groupMembers === null && mentionMode === "persona",
  );
  const teamMentionSearch = useTeamMentionSearch(
    mention.query,
    mention.isActive && groupMembers === null && mentionMode === "team",
  );
  const groupMatches =
    groupMembers?.filter(
      (member) =>
        member.status === "active" &&
        member.name
          .toLocaleLowerCase()
          .includes(mention.query.toLocaleLowerCase()),
    ) ?? [];
  const applyGroupMention = useCallback(
    (member: GroupMember) => {
      const before = input.substring(0, mention.atIndex);
      const after = input.substring(mention.atIndex + mention.query.length + 1);
      const sameName = groupMembers?.filter(
        (candidate) => candidate.name === member.name,
      ).length;
      const text =
        sameName === 1
          ? `@${member.name} `
          : `@[${member.name
              .replaceAll("[", "")
              .replaceAll("]", "")}](assistant:${member.id}) `;
      const nextInput = before + text + after;
      setSelectedMentionInput(nextInput.trim());
      setComposerPlainText(nextInput);
      setCursorPosition(before.length + text.length);
      focusComposerAtEnd();
      resetMention();
    },
    [
      input,
      mention,
      groupMembers,
      setComposerPlainText,
      setCursorPosition,
      focusComposerAtEnd,
      resetMention,
    ],
  );
  useEffect(() => {
    if (mention.isActive) {
      setMentionResultCount(
        groupMembers !== null
          ? groupMatches.length
          : mentionMode === "team"
            ? teamMentionSearch.teams.length
            : mentionSearch.presets.length,
      );
    }
  }, [
    mention.isActive,
    mentionMode,
    groupMembers,
    groupMatches.length,
    mentionSearch.presets.length,
    teamMentionSearch.teams.length,
    setMentionResultCount,
  ]);
  useEffect(() => {
    if (!onMentionQueryChange || groupMembers !== null) return;
    onMentionQueryChange(mention.isActive ? mention.query : null);
  }, [mention.isActive, mention.query, onMentionQueryChange, groupMembers]);
  useEffect(() => {
    const selectedId =
      mentionMode === "team" ? selectedTeamId : selectedPersonaPresetId;
    if (
      groupMembers !== null ||
      !onMentionQueryChange ||
      !selectedId ||
      !mention.isActive
    )
      return;
    const before = input.substring(0, mention.atIndex);
    const after = input.substring(mention.atIndex + mention.query.length + 1);
    setComposerPlainText(before + after);
    setCursorPosition(before.length || 0);
    focusComposerAtEnd();
    resetMention();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on selection
  }, [selectedPersonaPresetId, selectedTeamId, setComposerPlainText]);
  return {
    groupMembers,
    mentionEnabled,
    mention:
      selectedMentionInput === input.trim()
        ? { ...mention, isActive: false }
        : mention,
    mentionSearch,
    teamMentionSearch,
    groupMatches,
    applyGroupMention,
    moveMentionHighlight,
    setMentionHighlight,
    resetMention,
    dismissMention,
  };
}
