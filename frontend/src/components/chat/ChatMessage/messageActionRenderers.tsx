import { type ReactElement } from "react";
import {
  FeedbackMessageActionRenderer,
  type MessageActionRendererProps,
} from "./messageActionRendererComponents";

export const MESSAGE_ACTION_RENDERERS: Record<
  string,
  (props: MessageActionRendererProps) => ReactElement | null
> = {
  "feedback.FeedbackButtons": FeedbackMessageActionRenderer,
};

export type { MessageActionRendererProps };
