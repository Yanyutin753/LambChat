import { type ReactElement } from "react";
import type { CoreMessageActionContribution } from "../../../extensions/coreContributions";
import { FeedbackButtons } from "../../../plugins/feedback/FeedbackButtons";
import type { Message } from "../../../types";

export interface MessageActionRendererProps {
  contribution: CoreMessageActionContribution;
  sessionId: string;
  runId: string;
  currentFeedback: Message["feedback"];
  isLastMessage?: boolean;
}

export function FeedbackMessageActionRenderer({
  sessionId,
  runId,
  currentFeedback,
  isLastMessage,
}: MessageActionRendererProps): ReactElement {
  return (
    <FeedbackButtons
      sessionId={sessionId}
      runId={runId}
      currentFeedback={currentFeedback}
      isLastMessage={isLastMessage}
    />
  );
}
