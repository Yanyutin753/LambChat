import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetListParams,
  PersonaPresetListResponse,
  PersonaPresetSnapshot,
  PersonaPresetUpdate,
} from "../../types/personaPreset";

const PERSONA_PRESETS_API = `${API_BASE}/api/persona-presets`;

export function buildPersonaPresetListUrl(
  params: PersonaPresetListParams = {},
): string {
  const searchParams = new URLSearchParams();
  if (params.scope) searchParams.set("scope", params.scope);
  if (params.status) searchParams.set("status", params.status);
  if (params.q) searchParams.set("q", params.q);
  if (params.tag) searchParams.set("tag", params.tag);
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined)
    searchParams.set("limit", String(params.limit));

  const query = searchParams.toString();
  return `${PERSONA_PRESETS_API}/${query ? `?${query}` : ""}`;
}

export const personaPresetApi = {
  async list(
    params: PersonaPresetListParams = {},
  ): Promise<PersonaPresetListResponse> {
    return authFetch(buildPersonaPresetListUrl(params));
  },

  async get(presetId: string): Promise<PersonaPreset> {
    return authFetch(`${PERSONA_PRESETS_API}/${encodeURIComponent(presetId)}`);
  },

  async create(data: PersonaPresetCreate): Promise<PersonaPreset> {
    return authFetch(`${PERSONA_PRESETS_API}/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async update(
    presetId: string,
    data: PersonaPresetUpdate,
  ): Promise<PersonaPreset> {
    return authFetch(`${PERSONA_PRESETS_API}/${encodeURIComponent(presetId)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async delete(presetId: string): Promise<{ status: string }> {
    return authFetch(`${PERSONA_PRESETS_API}/${encodeURIComponent(presetId)}`, {
      method: "DELETE",
    });
  },

  async copy(presetId: string): Promise<PersonaPreset> {
    return authFetch(
      `${PERSONA_PRESETS_API}/${encodeURIComponent(presetId)}/copy`,
      {
        method: "POST",
      },
    );
  },

  async use(presetId: string): Promise<PersonaPresetSnapshot> {
    return authFetch(
      `${PERSONA_PRESETS_API}/${encodeURIComponent(presetId)}/use`,
      {
        method: "POST",
      },
    );
  },
};
