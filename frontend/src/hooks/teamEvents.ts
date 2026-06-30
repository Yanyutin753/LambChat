export const TEAMS_CHANGED_EVENT = "teams-changed";

export interface TeamsChangedDetail {
  action?: "created" | "updated" | "deleted";
  teamId?: string;
  teamName?: string;
}

export type TeamEventTarget = Pick<
  EventTarget,
  "addEventListener" | "removeEventListener" | "dispatchEvent"
>;

function buildCustomEvent(detail: TeamsChangedDetail): Event {
  if (typeof CustomEvent !== "undefined") {
    return new CustomEvent<TeamsChangedDetail>(TEAMS_CHANGED_EVENT, {
      detail,
    });
  }

  const event = new Event(TEAMS_CHANGED_EVENT);
  Object.defineProperty(event, "detail", {
    configurable: true,
    enumerable: true,
    value: detail,
  });
  return event;
}

function getDefaultEventTarget(): TeamEventTarget | null {
  if (typeof window === "undefined") return null;
  return window;
}

export function dispatchTeamsChanged(
  detail: TeamsChangedDetail,
  target: TeamEventTarget | null = getDefaultEventTarget(),
): boolean {
  if (!target) return false;
  return target.dispatchEvent(buildCustomEvent(detail));
}

export function subscribeTeamsChanged(
  listener: (detail: TeamsChangedDetail) => void,
  target: TeamEventTarget | null = getDefaultEventTarget(),
): () => void {
  if (!target) return () => {};

  const handler = (event: Event) => {
    const detail =
      "detail" in event
        ? (event as CustomEvent<TeamsChangedDetail>).detail ?? {}
        : {};
    listener(detail);
  };

  target.addEventListener(TEAMS_CHANGED_EVENT, handler as EventListener);
  return () => {
    target.removeEventListener(TEAMS_CHANGED_EVENT, handler as EventListener);
  };
}
