import { type ReactElement } from "react";
import { FeedbackButtons } from "../../../plugins/feedback/FeedbackButtons";
import type { Message } from "../../../types";
import type { CoreMessageActionContribution } from "../../../extensions/coreContributions";

export interface MessageActionRendererProps {
  contribution: CoreMessageActionContribution;
  sessionId: string;
  runId: string;
  currentFeedback: Message["feedback"];
  isLastMessage?: boolean;
}

function FeedbackMessageActionRenderer({
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

export const MESSAGE_ACTION_RENDERERS: Record<
  string,
  (props: MessageActionRendererProps) => ReactElement | null
> = {
  "feedback.FeedbackButtons": FeedbackMessageActionRenderer,
};
