export const PERSONA_PRESETS_CHANGED_EVENT = "persona-presets-changed";

export interface PersonaPresetsChangedDetail {
  action?: "created" | "updated" | "deleted";
  presetId?: string;
  presetName?: string;
}

export type PersonaPresetEventTarget = Pick<
  EventTarget,
  "addEventListener" | "removeEventListener" | "dispatchEvent"
>;

function buildCustomEvent(detail: PersonaPresetsChangedDetail): Event {
  if (typeof CustomEvent !== "undefined") {
    return new CustomEvent<PersonaPresetsChangedDetail>(
      PERSONA_PRESETS_CHANGED_EVENT,
      { detail },
    );
  }

  const event = new Event(PERSONA_PRESETS_CHANGED_EVENT);
  Object.defineProperty(event, "detail", {
    configurable: true,
    enumerable: true,
    value: detail,
  });
  return event;
}

function getDefaultEventTarget(): PersonaPresetEventTarget | null {
  if (typeof window === "undefined") return null;
  return window;
}

export function dispatchPersonaPresetsChanged(
  detail: PersonaPresetsChangedDetail,
  target: PersonaPresetEventTarget | null = getDefaultEventTarget(),
): boolean {
  if (!target) return false;
  return target.dispatchEvent(buildCustomEvent(detail));
}

export function subscribePersonaPresetsChanged(
  listener: (detail: PersonaPresetsChangedDetail) => void,
  target: PersonaPresetEventTarget | null = getDefaultEventTarget(),
): () => void {
  if (!target) return () => {};

  const handler = (event: Event) => {
    const detail =
      "detail" in event
        ? (event as CustomEvent<PersonaPresetsChangedDetail>).detail ?? {}
        : {};
    listener(detail);
  };

  target.addEventListener(
    PERSONA_PRESETS_CHANGED_EVENT,
    handler as EventListener,
  );
  return () => {
    target.removeEventListener(
      PERSONA_PRESETS_CHANGED_EVENT,
      handler as EventListener,
    );
  };
}
