import { type PersonaPresetEventTarget } from "../../../../hooks/personaPresetEvents";
import {
  dispatchToolMutationRefresh,
  getPersonaPresetMutationDetail,
} from "./toolMutationEvents";

export { getPersonaPresetMutationDetail };

export function dispatchPersonaPresetRefreshFromToolResult(
  result: string | Record<string, unknown> | undefined,
  target?: PersonaPresetEventTarget | null,
): boolean {
  return dispatchToolMutationRefresh(result, { persona: target });
}
